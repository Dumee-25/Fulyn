"""The memory layer: one searchable row per memorable domain record.

Search is hybrid. Vector similarity alone ranks unrelated text highly (a query about a
person who never appears still gets ~0.6 similarity), so results are fused with Postgres
full-text matches using reciprocal rank fusion, nudged by importance, and each result
says whether it actually contains the query's words.
"""

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models.journal import JournalEntry
from app.models.memory import Memory
from app.models.people import MusicMemory, Person, PersonInteraction
from app.models.planning import Decision
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
) -> Memory:
    """Create or refresh the memory for a source record, re-embedding if its text changed."""
    memory = db.scalar(
        select(Memory).where(Memory.memory_type == memory_type, Memory.source_id == source_id)
    )
    if memory is None:
        memory = Memory(memory_type=memory_type, source_id=source_id, content=content)
        db.add(memory)
    text_changed = memory.content != content or memory.title != title or memory.id is None
    memory.title = title
    memory.content = content
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


def _journal_is_private(db: Session, journal_entry_id: uuid.UUID | None) -> bool:
    if journal_entry_id is None:
        return False
    entry = db.get(JournalEntry, journal_entry_id)
    return bool(entry and entry.is_private)


def sync_journal_memory(db: Session, entry: JournalEntry) -> Memory:
    memory = upsert_memory(
        db,
        memory_type="journal",
        source_id=entry.id,
        title=entry.ai_summary or _title_from(entry.raw_text),
        content=entry.raw_text,
        memory_date=entry.entry_date,
        importance_score=entry.importance_score,
        is_private=entry.is_private,
    )
    _propagate_privacy(db, entry)
    return memory


def _propagate_privacy(db: Session, entry: JournalEntry) -> None:
    """Records that came from a private journal entry are private too."""
    linked = [
        (
            "person_interaction",
            select(PersonInteraction.id).where(PersonInteraction.journal_entry_id == entry.id),
        ),
        ("music", select(MusicMemory.id).where(MusicMemory.journal_entry_id == entry.id)),
        ("decision", select(Decision.id).where(Decision.journal_entry_id == entry.id)),
    ]
    for memory_type, ids in linked:
        for memory in db.scalars(
            select(Memory).where(Memory.memory_type == memory_type, Memory.source_id.in_(ids))
        ):
            memory.is_private = entry.is_private
    db.commit()


def sync_interaction_memory(db: Session, interaction: PersonInteraction) -> Memory:
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
        is_private=_journal_is_private(db, interaction.journal_entry_id),
    )


def sync_music_memory(db: Session, music: MusicMemory) -> Memory:
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
        is_private=_journal_is_private(db, music.journal_entry_id),
    )


def sync_decision_memory(db: Session, decision: Decision) -> Memory:
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
        is_private=_journal_is_private(db, decision.journal_entry_id),
    )


def delete_memories_for(db: Session, memory_type: str, source_id: uuid.UUID) -> None:
    for memory in db.scalars(
        select(Memory).where(Memory.memory_type == memory_type, Memory.source_id == source_id)
    ):
        db.delete(memory)
    db.commit()


# --- Embeddings ------------------------------------------------------------------


def _embedding_text(memory: Memory) -> str:
    if memory.title and not memory.content.startswith(memory.title):
        return f"{memory.title}\n{memory.content}"
    return memory.content


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
    include_private: bool,
) -> Select[Any]:
    if not include_private:
        stmt = stmt.where(Memory.is_private.is_(False))
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
    include_private: bool = False,
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
        include_private=include_private,
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
    include_private: bool = False,
    limit: int = 10,
) -> MemorySearchResponse:
    filters = {
        "date_from": date_from,
        "date_to": date_to,
        "min_importance": min_importance,
        "memory_type": memory_type,
        "include_private": include_private,
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
IMPORTANCE_SOURCES: dict[str, type] = {
    "journal": JournalEntry,
    "person_interaction": PersonInteraction,
    "music": MusicMemory,
    "decision": Decision,
}


def update_memory(db: Session, memory_id: uuid.UUID, data: MemoryUpdate) -> Memory:
    """Importance is kept in step with the source record."""
    memory = get_memory(db, memory_id)
    changes = data.changes()
    source_model = IMPORTANCE_SOURCES.get(memory.memory_type)
    if "importance_score" in changes and source_model and memory.source_id:
        source = db.get(source_model, memory.source_id)
        if source is not None:
            source.importance_score = changes["importance_score"]
    if "title" in changes and changes["title"] != memory.title:
        memory.embedding = None
        memory.embedding_model = None
    memory = crud.apply_changes(db, memory, changes)
    if memory.embedding is None:
        embed_memories(db, [memory])
    return memory


def set_memory_importance(db: Session, memory_id: uuid.UUID, importance_score: int) -> Memory:
    return update_memory(db, memory_id, MemoryUpdate(importance_score=importance_score))
