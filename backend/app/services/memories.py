"""The memory layer: one searchable row per moment (see "Sync from domain records").

Search is hybrid. Vector similarity alone ranks unrelated text highly (a query about a
person who never appears still gets ~0.6 similarity), so results are fused with Postgres
full-text matches using reciprocal rank fusion, nudged by importance, and each result
says whether it actually contains the query's words.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.journal import JournalEntry
from app.models.memory import Memory
from app.models.people import MusicMemory, Person, PersonInteraction
from app.models.planning import Decision
from app.models.report import LifeEvent
from app.schemas.memory import MemorySearchResponse, MemorySearchResult, MemoryUpdate
from app.services import crud
from app.services.embeddings import EmbeddingUnavailableError, get_embedding_service

logger = logging.getLogger(__name__)

RRF_K = 60
CANDIDATES = 50
# Added per importance point on top of RRF scores (~0.016 for a top hit).
IMPORTANCE_BOOST = 0.002
TITLE_MAX = 200


# --- Sync from domain records ----------------------------------------------------
#
# One memory per moment. A chat message that logs a journal entry plus an interaction and
# a life event is one moment, so only the journal entry's memory represents it; its tags
# carry the linked people, places, events, songs and decisions so search still finds it.
# Records without a journal entry (added on their own page) keep a memory of their own.

# Record types that can belong to a journal entry's moment, by memory_type.
MOMENT_MODELS: dict[str, type] = {
    "person_interaction": PersonInteraction,
    "event": LifeEvent,
    "music": MusicMemory,
    "decision": Decision,
}


def _title_from(text: str) -> str:
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    return first_line[: TITLE_MAX - 1] + "…" if len(first_line) > TITLE_MAX else first_line


def upsert_memory(
    db: Session,
    *,
    memory_type: str,
    source_id: uuid.UUID,
    title: str | None,
    content: str,
    memory_date: date,
    importance_score: int,
    is_private: bool,
    tags: list[str] | None = None,
) -> Memory:
    """Create or refresh the memory for a source record, re-embedding if its text changed."""
    memory = db.scalar(
        select(Memory).where(Memory.memory_type == memory_type, Memory.source_id == source_id)
    )
    if memory is None:
        memory = Memory(memory_type=memory_type, source_id=source_id, content=content)
        db.add(memory)
    tag_text = "\n".join(tags) if tags else None
    text_changed = (
        memory.content != content
        or memory.title != title
        or memory.tags != tag_text
        or memory.id is None
    )
    memory.title = title
    memory.content = content
    memory.tags = tag_text
    memory.memory_date = memory_date
    memory.importance_score = importance_score
    memory.is_private = is_private
    if text_changed:
        memory.embedding = None
        memory.embedding_model = None
    db.commit()
    if memory.embedding is None:
        embed_memories(db, [memory])
    return memory


def moment_records(db: Session, journal_entry_id: uuid.UUID) -> list[Any]:
    """Interactions, events, music and decisions logged as part of a journal entry."""
    records: list[Any] = []
    for model in MOMENT_MODELS.values():
        records += db.scalars(
            select(model)
            .where(model.journal_entry_id == journal_entry_id)
            .order_by(model.created_at, model.id)
        )
    return records


def moment_tags(db: Session, records: list[Any]) -> list[str]:
    """Names, places, event, song and decision titles, in that order, without repeats."""
    tags: list[str] = []
    for record in records:
        if isinstance(record, PersonInteraction):
            person = db.get(Person, record.person_id)
            tags += [person.name if person else None, record.location]
        elif isinstance(record, LifeEvent):
            tags.append(record.title)
        elif isinstance(record, MusicMemory):
            person = db.get(Person, record.person_id) if record.person_id else None
            tags += [
                record.song + (f" by {record.artist}" if record.artist else ""),
                person.name if person else None,
            ]
        elif isinstance(record, Decision):
            tags.append(record.title)
    seen: set[str] = set()
    unique = []
    for tag in tags:
        tag = " ".join((tag or "").split())[:TITLE_MAX]
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            unique.append(tag)
    return unique


def _drop_record_memories(db: Session, records: list[Any]) -> None:
    """Records in a moment are represented by the journal entry's memory, not their own."""
    for memory_type, model in MOMENT_MODELS.items():
        ids = [r.id for r in records if isinstance(r, model)]
        if ids:
            db.execute(
                delete(Memory).where(Memory.memory_type == memory_type, Memory.source_id.in_(ids))
            )


def sync_journal_memory(db: Session, entry: JournalEntry) -> Memory:
    records = moment_records(db, entry.id)
    _drop_record_memories(db, records)
    return upsert_memory(
        db,
        memory_type="journal",
        source_id=entry.id,
        title=entry.ai_summary or _title_from(entry.raw_text),
        content=entry.raw_text,
        memory_date=entry.entry_date,
        importance_score=entry.importance_score,
        # Vault content is decided by the journal entry alone.
        is_private=entry.is_private,
        tags=moment_tags(db, records),
    )


def resync_moment(db: Session, journal_entry_id: uuid.UUID | None) -> None:
    """Refresh a journal entry's memory after a record joined, changed or left it."""
    entry = db.get(JournalEntry, journal_entry_id) if journal_entry_id else None
    if entry is not None:
        sync_journal_memory(db, entry)


def set_moment_importance(db: Session, journal_entry_id: uuid.UUID, score: int) -> Memory:
    """Importance belongs to the moment: the entry and every record logged with it."""
    entry = crud.get_or_raise(db, JournalEntry, journal_entry_id)
    entry.importance_score = score
    for record in moment_records(db, entry.id):
        record.importance_score = score
    db.commit()
    return sync_journal_memory(db, entry)


def _sync_record(
    db: Session,
    record: Any,
    standalone: Callable[[], Memory],
    *,
    previous_entry_id: uuid.UUID | None,
    importance_changed: bool,
) -> Memory:
    """Give an unlinked record its own memory, or fold a linked one into its moment.

    Otherwise the moment takes the highest importance among the entry and its records, so
    records that join it never lower it; an explicit importance change on a linked record
    sets the whole moment to that value.
    """
    entry = db.get(JournalEntry, record.journal_entry_id) if record.journal_entry_id else None
    if entry is None:
        memory = standalone()
    else:
        if importance_changed:
            score = record.importance_score
        else:
            linked = [r.importance_score for r in moment_records(db, entry.id)]
            score = max([entry.importance_score, *linked])
        memory = set_moment_importance(db, entry.id, score)
    if previous_entry_id is not None and previous_entry_id != record.journal_entry_id:
        resync_moment(db, previous_entry_id)
    return memory


def sync_interaction_memory(
    db: Session,
    interaction: PersonInteraction,
    *,
    previous_entry_id: uuid.UUID | None = None,
    importance_changed: bool = False,
) -> Memory:
    def standalone() -> Memory:
        person = db.get(Person, interaction.person_id)
        name = person.name if person else "someone"
        parts = [interaction.summary]
        if interaction.location:
            parts.append(f"Location: {interaction.location}")
        if interaction.raw_context and interaction.raw_context != interaction.summary:
            parts.append(interaction.raw_context)
        return upsert_memory(
            db,
            memory_type="person_interaction",
            source_id=interaction.id,
            title=f"With {name}",
            content="\n".join(parts),
            memory_date=interaction.interaction_date,
            importance_score=interaction.importance_score,
            is_private=False,
        )

    return _sync_record(
        db,
        interaction,
        standalone,
        previous_entry_id=previous_entry_id,
        importance_changed=importance_changed,
    )


def sync_music_memory(
    db: Session,
    music: MusicMemory,
    *,
    previous_entry_id: uuid.UUID | None = None,
    importance_changed: bool = False,
) -> Memory:
    def standalone() -> Memory:
        person = db.get(Person, music.person_id) if music.person_id else None
        title = music.song + (f" by {music.artist}" if music.artist else "")
        parts = [title]
        if music.album:
            parts.append(f"Album: {music.album}")
        if music.memory_text:
            parts.append(music.memory_text)
        if music.emotion:
            parts.append(f"Feeling: {music.emotion}")
        if person:
            parts.append(f"Connected to {person.name}")
        return upsert_memory(
            db,
            memory_type="music",
            source_id=music.id,
            title=title[:TITLE_MAX],
            content="\n".join(parts),
            memory_date=music.memory_date,
            importance_score=music.importance_score,
            is_private=False,
        )

    return _sync_record(
        db,
        music,
        standalone,
        previous_entry_id=previous_entry_id,
        importance_changed=importance_changed,
    )


def sync_decision_memory(
    db: Session,
    decision: Decision,
    *,
    previous_entry_id: uuid.UUID | None = None,
    importance_changed: bool = False,
) -> Memory:
    def standalone() -> Memory:
        parts = [decision.decision]
        if decision.reasoning:
            parts.append(f"Why: {decision.reasoning}")
        if decision.status != "active":
            parts.append(f"Status: {decision.status}")
        return upsert_memory(
            db,
            memory_type="decision",
            source_id=decision.id,
            title=decision.title[:TITLE_MAX],
            content="\n".join(parts),
            memory_date=decision.decision_date,
            importance_score=decision.importance_score,
            is_private=False,
        )

    return _sync_record(
        db,
        decision,
        standalone,
        previous_entry_id=previous_entry_id,
        importance_changed=importance_changed,
    )


def sync_event_memory(
    db: Session,
    event: LifeEvent,
    *,
    previous_entry_id: uuid.UUID | None = None,
    importance_changed: bool = False,
) -> Memory:
    def standalone() -> Memory:
        parts = [event.title]
        if event.description:
            parts.append(event.description)
        if event.event_type:
            parts.append(f"Type: {event.event_type}")
        return upsert_memory(
            db,
            memory_type="event",
            source_id=event.id,
            title=event.title[:TITLE_MAX],
            content="\n".join(parts),
            memory_date=event.event_date,
            importance_score=event.importance_score,
            is_private=False,
        )

    return _sync_record(
        db,
        event,
        standalone,
        previous_entry_id=previous_entry_id,
        importance_changed=importance_changed,
    )


def sync_record_memory(db: Session, record: Any, **kwargs: Any) -> Memory:
    """Sync any moment-capable record (used when records are linked after the fact)."""
    sync = {
        PersonInteraction: sync_interaction_memory,
        LifeEvent: sync_event_memory,
        MusicMemory: sync_music_memory,
        Decision: sync_decision_memory,
    }[type(record)]
    return sync(db, record, **kwargs)


def delete_memories_for(
    db: Session,
    memory_type: str,
    source_id: uuid.UUID,
    journal_entry_id: uuid.UUID | None = None,
) -> None:
    """Remove a deleted record's memory; if it was part of a moment, refresh that moment."""
    for memory in db.scalars(
        select(Memory).where(Memory.memory_type == memory_type, Memory.source_id == source_id)
    ):
        db.delete(memory)
    db.commit()
    resync_moment(db, journal_entry_id)


# --- Embeddings ------------------------------------------------------------------


def _embedding_text(memory: Memory) -> str:
    text = memory.content
    if memory.title and not memory.content.startswith(memory.title):
        text = f"{memory.title}\n{text}"
    if memory.tags:
        text += "\n" + ", ".join(memory.tags.splitlines())
    return text


def embed_memories(db: Session, memories: list[Memory]) -> int:
    """Embed the given memories. Failures leave them pending; never raises."""
    service = get_embedding_service()
    if service is None or not memories:
        return 0
    try:
        vectors = service.embed([_embedding_text(m) for m in memories], "document")
    except EmbeddingUnavailableError:
        return 0
    for memory, vector in zip(memories, vectors, strict=True):
        memory.embedding = vector
        memory.embedding_model = service.model
    db.commit()
    return len(memories)


def backfill_embeddings(db: Session, limit: int = 100) -> int:
    """Embed memories that have no embedding or one from a different model."""
    service = get_embedding_service()
    if service is None:
        return 0
    pending = list(
        db.scalars(
            select(Memory)
            .where(or_(Memory.embedding.is_(None), Memory.embedding_model != service.model))
            .order_by(Memory.created_at)
            .limit(limit)
        )
    )
    return embed_memories(db, pending)


# --- Reading ---------------------------------------------------------------------


def get_memory(db: Session, memory_id: uuid.UUID) -> Memory:
    return crud.get_or_raise(db, Memory, memory_id)


def _filtered(
    stmt: Select[Any],
    *,
    date_from: date | None,
    date_to: date | None,
    min_importance: int | None,
    memory_type: str | None,
    private: bool,
) -> Select[Any]:
    # Normal and vault searches never mix: private=True returns vault memories only.
    stmt = stmt.where(Memory.is_private.is_(private))
    stmt = crud.date_range(stmt, Memory.memory_date, date_from, date_to)
    if min_importance is not None:
        stmt = stmt.where(Memory.importance_score >= min_importance)
    if memory_type is not None:
        stmt = stmt.where(Memory.memory_type == memory_type)
    return stmt


def list_memories(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    min_importance: int | None = None,
    memory_type: str | None = None,
    private: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[Memory]:
    """Most important first, then most recent."""
    stmt = _filtered(
        select(Memory),
        date_from=date_from,
        date_to=date_to,
        min_importance=min_importance,
        memory_type=memory_type,
        private=private,
    ).order_by(Memory.importance_score.desc(), Memory.memory_date.desc())
    return crud.paginate(db, stmt, limit, offset)


def _keyword_query(query: str) -> Any:
    # Any word may match ("memories about Sarah" -> memori | sarah); stopwords are dropped.
    words = [w for w in query.replace('"', " ").split() if w.strip("-")]
    return func.websearch_to_tsquery("english", " or ".join(words))


def search_memories(
    db: Session,
    query: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    min_importance: int | None = None,
    memory_type: str | None = None,
    private: bool = False,
    limit: int = 10,
) -> MemorySearchResponse:
    filters = {
        "date_from": date_from,
        "date_to": date_to,
        "min_importance": min_importance,
        "memory_type": memory_type,
        "private": private,
    }

    # Full-text candidates.
    tsquery = _keyword_query(query)
    rank = func.ts_rank(Memory.search_vector, tsquery)
    keyword_rows = db.execute(
        _filtered(select(Memory.id, rank), **filters)
        .where(Memory.search_vector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(CANDIDATES)
    ).all()

    # Vector candidates, when an embedding model is available.
    semantic = False
    similarities: dict[uuid.UUID, float] = {}
    vector_rows: list[Any] = []
    service = get_embedding_service()
    if service is not None:
        try:
            backfill_embeddings(db, limit=50)
            (query_vector,) = service.embed([query], "query")
            semantic = True
        except EmbeddingUnavailableError:
            query_vector = None
        if query_vector is not None:
            distance = Memory.embedding.cosine_distance(query_vector)
            vector_rows = db.execute(
                _filtered(select(Memory.id, distance), **filters)
                .where(Memory.embedding.is_not(None))
                .order_by(distance)
                .limit(CANDIDATES)
            ).all()
            similarities = {row[0]: 1 - float(row[1]) for row in vector_rows}

    scores: dict[uuid.UUID, float] = {}
    for ranked in (keyword_rows, vector_rows):
        for position, row in enumerate(ranked):
            scores[row[0]] = scores.get(row[0], 0.0) + 1 / (RRF_K + position + 1)
    if not scores:
        return MemorySearchResponse(query=query, semantic=semantic, results=[])

    memories = {m.id: m for m in db.scalars(select(Memory).where(Memory.id.in_(scores)))}
    for memory_id, memory in memories.items():
        scores[memory_id] += IMPORTANCE_BOOST * memory.importance_score
    keyword_ids = {row[0] for row in keyword_rows}
    ordered = sorted(memories, key=lambda mid: scores[mid], reverse=True)[:limit]
    results = [
        MemorySearchResult.model_validate(memories[mid]).model_copy(
            update={
                "similarity": round(similarities[mid], 3) if mid in similarities else None,
                "keyword_match": mid in keyword_ids,
            }
        )
        for mid in ordered
    ]
    return MemorySearchResponse(query=query, semantic=semantic, results=results)


# --- Changes ---------------------------------------------------------------------

# Memory types whose source record carries its own importance_score.
IMPORTANCE_SOURCES: dict[str, type] = {"journal": JournalEntry, **MOMENT_MODELS}


def _set_source_importance(db: Session, memory: Memory, score: int) -> None:
    """A journal memory stands for a moment: the entry and everything logged with it."""
    source_model = IMPORTANCE_SOURCES.get(memory.memory_type)
    source = db.get(source_model, memory.source_id) if source_model and memory.source_id else None
    if source is None:
        return
    entry_id = source.id if isinstance(source, JournalEntry) else source.journal_entry_id
    if entry_id is not None:
        set_moment_importance(db, entry_id, score)
    else:
        source.importance_score = score


def update_memory(db: Session, memory_id: uuid.UUID, data: MemoryUpdate) -> Memory:
    """Importance is kept in step with the source record (the whole moment for a journal)."""
    memory = get_memory(db, memory_id)
    changes = data.changes()
    if "importance_score" in changes:
        _set_source_importance(db, memory, changes["importance_score"])
        memory = get_memory(db, memory_id)
    if "title" in changes and changes["title"] != memory.title:
        memory.embedding = None
        memory.embedding_model = None
    memory = crud.apply_changes(db, memory, changes)
    if memory.embedding is None:
        embed_memories(db, [memory])
    return memory


def set_memory_importance(db: Session, memory_id: uuid.UUID, importance_score: int) -> Memory:
    return update_memory(db, memory_id, MemoryUpdate(importance_score=importance_score))
