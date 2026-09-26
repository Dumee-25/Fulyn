# Fulyn

Fulyn is a private, single-user AI agent that remembers your life. You type naturally
("Spent 850 on dinner, slept about 4 hours, met Alex after uni"), and Fulyn extracts
structured records (expenses, sleep, mood, people, journal) and stores them so it can
answer questions about them later.

The full design lives in [`Personal Life Agent — Build Specification.md`](./Personal%20Life%20Agent%20—%20Build%20Specification.md).

## Status

| Phase | Scope | State |
| --- | --- | --- |
| 1 | Foundation: repo layout, FastAPI, PostgreSQL + pgvector, SQLAlchemy, Alembic, Next.js, Tailwind, shadcn/ui, Docker Compose, config, health check | Done |
| 2 | Core life logging: journal, expenses, mood, sleep, caffeine (models, CRUD API, pages) | Done |
| 3 | Agent: Ollama client, system prompt, tool registry, agent loop, chat endpoint and page | Done |
| 4 | Memory: memory table, local embeddings, hybrid semantic + full-text search, importance | Done |
| 5 | People and music: people, interactions, music memories, linked into memory search | Done |
| 6 | Personal management: subscriptions, reminders, decisions, waiting items, impulse purchases | Done |
| 7 | Timeline and reports: life events, life timeline, daily and weekly recaps, monthly report | Done |
| 8 | Analytics: dashboard charts and cross-domain analytics | Next |
| 9–10 | people and music, personal management, reports, analytics, vault, export | Planned |

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, Pydantic v2, Alembic, psycopg 3
- **Database:** PostgreSQL 17 with pgvector
- **AI:** Ollama, configured through `OLLAMA_BASE_URL` and `OLLAMA_MODEL`
- **Frontend:** Next.js 16 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui

## Layout

```text
backend/
  app/
    api/        # routers (thin: no domain logic)
    agent/      # Ollama client, system prompt, agent loop
    core/       # settings, logging, time helpers, domain errors
    db/         # engine, session, declarative base and mixins, dev seed
    models/     # ORM models (import them in models/__init__.py for Alembic)
    schemas/    # Pydantic request/response schemas
    services/   # domain logic
    tools/      # tool registry and the tools the agent may call
    reports/    # recaps and reports (Phase 7)
    exports/    # data export (Phase 10)
  alembic/      # migrations
  tests/
frontend/
  app/ components/ hooks/ lib/ types/
docker-compose.yml
.env.example
```

## Getting started

### 1. Configure

```bash
cp .env.example .env
```

Set `POSTGRES_PASSWORD` (and the matching password inside `DATABASE_URL`). If port
5432 is already taken on your machine, change `POSTGRES_PORT` and the port in `DATABASE_URL`.

### 2. Run everything with Docker Compose

```bash
docker compose up -d --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 (interactive docs at `/docs`)
- Health check: http://localhost:8000/api/health

The backend container runs `alembic upgrade head` on start. Source directories are
bind-mounted. The backend reloads on changes. The frontend container may not see
file changes on Windows/macOS bind mounts; restart it (`docker compose restart frontend`)
or run the frontend on the host (below) for reliable hot reload.

Ollama is not part of Compose. Run it on the host; the backend reaches it at
`http://host.docker.internal:11434` (override with `OLLAMA_DOCKER_URL`).

### 3. Or run the apps on the host

Start only the database, then run the backend and frontend yourself:

```bash
docker compose up -d db
```

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

On Windows, use `127.0.0.1` rather than `localhost` in `DATABASE_URL`: `localhost`
resolves to IPv6 first and the connection can hang.

The Next.js server proxies every `/api/*` request to `BACKEND_URL`
(default `http://localhost:8000`), so the browser only ever talks to one origin.

## Tests and linting

```bash
cd backend && pytest && ruff check . && ruff format --check .
```

Agent tests use a scripted fake model, so they are fast and deterministic; a test fixture
makes it impossible for them to reach the real model. Tests against the real configured
model are opt-in (they depend on the model, so an occasional run can differ):

```bash
cd backend && RUN_LLM_TESTS=1 pytest -m llm
```

API tests use a separate database (`<db>_test`, or `TEST_DATABASE_URL`) that is created
automatically; each test runs in a rolled-back transaction. If PostgreSQL is not running,
those tests are skipped.

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

## Migrations

```bash
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Revision `0001` enables the `vector` extension; `0002` adds the core logging tables;
`0003` adds chat conversations; `0004` adds memories (and creates memories for existing
journal entries); `0005` adds people, interactions and music memories; `0006` adds subscriptions,
reminders, decisions and waiting items; `0007` adds life events and stored reports.

## The agent

Open http://localhost:3000/chat and write naturally, for example:

> Slept around 2 last night and woke at 7. Had an iced latte at 10. Went to Barista with
> Maya after uni and spent 1450. Pretty nice day honestly.

Fulyn saves the message as a journal entry and creates the sleep, caffeine, expense and
mood records it describes, all linked to that entry. Corrections work in the same
conversation ("Actually the Barista bill was 1550", "Make that evening a core memory").

How it works (`backend/app/agent/loop.py`):

1. Load the recent conversation (`AGENT_HISTORY_MESSAGES`) and build the system prompt with
   the current local time, timezone, currency and categories.
2. Send it to Ollama with the tool schemas (`OLLAMA_MODEL`, native tool calling).
3. Validate each tool call against its Pydantic model and run the matching service.
   Invalid arguments and errors go back to the model as tool results so it can retry.
4. Repeat until the model answers without tool calls, at most `AGENT_MAX_TOOL_ITERATIONS`
   (default 8) rounds.

Guarantees enforced in code rather than left to the prompt:

- The model never writes SQL; it can only call the registered tools (`app/tools/`).
- `create_journal_entry` takes no text argument. It always stores the user's message
  verbatim, so the model cannot paraphrase or replace it. Updates cannot change it either.
- Every record created in a turn is linked to that turn's journal entry. If the model
  logs something but forgets the journal entry, the backend saves the message itself.
- Journal search tools never return private entries.
- Tool results show times in local time, so the model does not have to convert from UTC.

Chat transcripts (including tool calls) are stored in `conversations` and
`chat_messages` so later messages can refer back to earlier records.

## Memory

Every journal entry is mirrored into the `memories` table, the single searchable index
(later phases add events, interactions, decisions and music). Each memory stores the text,
date, importance (0 disposable … 5 core memory), privacy flag, a 768-dimension embedding
and a generated full-text vector.

**Search is hybrid.** Testing `nomic-embed-text` showed that vector similarity alone is not
trustworthy here: a query about a person who never appears ("what happened with John")
scored 0.62 against unrelated entries, higher than some real matches, and a name barely
moves the ranking. So `search_memories` runs both a pgvector cosine search and a Postgres
full-text search, merges them with reciprocal rank fusion, adds a small boost per
importance point, and marks each result with `keyword_match`. The agent is told that
semantic-only neighbours are not evidence. Conceptual queries still work: "rainy evening"
finds "Uber home because it was raining".

- Embeddings are made by `OLLAMA_EMBED_MODEL` (default setup: `nomic-embed-text`, local).
  If it is unset or unreachable, entries are still saved and search falls back to
  full-text only; missing embeddings are filled in on the next search or with
  `POST /api/memories/backfill`. Changing the embedding model re-embeds automatically;
  a model with a different dimension needs a migration (`EMBEDDING_DIMENSIONS` in
  `app/models/memory.py`).
- Importance stays in sync both ways: changing a memory updates its journal entry and
  vice versa. "Remember this" and "make that a core memory" set it to 5.
- Private entries are never returned by memory listing, search, `GET /api/memories/{id}`
  or the agent's search tool. Vault search comes in Phase 9.

## People and music

- **People** hold only what you have said: name, nickname, relationship (only if stated),
  notes. `first_mentioned_at` and `last_interaction_at` are kept up to date from
  interactions. People are listed alphabetically and never scored or ranked.
- **Name matching:** the agent passes names as you said them. The backend matches an exact
  name or nickname first, then a first name ("Sarah" → "Sarah Perera"), and creates the
  person if nobody matches. If several people match, the tool returns the candidates and
  the agent asks which one you mean.
- **Interactions** store a summary, place, date, importance and `raw_context`, which is
  always your own message verbatim (the model cannot write it). One interaction per
  person, so "met Maya and Alex" creates two.
- **Music memories** link a song to a date, feeling, text and optionally a person.
  `GET /api/music/top` (and the agent's music search with a date range) returns the
  most-mentioned songs, e.g. "what songs defined September?".
- **Semantic linking:** interactions and music memories are mirrored into `memories`
  (titles like "With Maya" and "Yellow by Coldplay", contents include the person's name),
  so memory search finds them next to journal entries. Renaming a person refreshes those
  memories, and records that came from a private journal entry are private too.
- Deleting a person deletes their interactions; music memories stay, unlinked.

## Planning

- **Subscriptions** store the price and billing cycle (weekly, monthly, quarterly, yearly or
  custom every N days). The API derives `monthly_cost` (exact decimals, rounded half-up to
  cents) and `next_due`, the next billing date on or after today, rolled forward from the
  stored date. Totals are per currency and never converted. Cancelling sets
  `active = false` and keeps the record.
- **Reminders** have a local `due_at`, an optional `recurrence_rule` (daily, weekly,
  monthly, yearly) and a status. Completing a one-off reminder marks it completed;
  completing a recurring one moves it to its next occurrence after now, skipping missed
  ones. There are no push notifications yet: reminders show on the Reminders page and the
  dashboard. A future notifier only needs `GET /api/reminders?due_before=<now>` (indexed
  on status and due_at).
- **Decisions** keep the decision and the reasoning in your words, with a status (active,
  reconsidered, reversed, completed). They are mirrored into memory search, so "why did I
  decide not to buy the keyboard?" finds them.
- **Waiting items** track refunds, deliveries, replies and so on, optionally from a person,
  with an expected date. Items past their expected date are flagged `overdue` but not
  changed automatically.
- **Impulse purchases** use `expenses.is_impulse` and `impulse_reason`. The agent only
  sets it when you say so, clears it when you say it wasn't, and is told never to judge
  spending. On the Expenses page, click "impulse" on a row to toggle it; the monthly
  summary shows impulse spending separately.

## Timeline and reports

- **Life events** record outings and milestones ("Barista with Maya", "passed the driving
  test"); the agent creates them for notable occasions, not routine ones. They are part
  of memory search.
- **Timeline** (`/timeline`) merges life events, decisions, interactions and music memories
  at or above a minimum importance (default 2), journal entries only when notable (3+),
  and expenses at or above `MAJOR_PURCHASE_AMOUNT` (default Rs. 10,000). So a normal coffee
  never appears.
- **Reports** (`/reports`): daily recap, weekly recap (Monday–Sunday, compared with the week
  before) and monthly life report. They are generated on demand and stored; generating
  again replaces the stored version.
- **Facts come from code, prose from the model.** Every number and list in a report is
  computed by SQL in `app/reports/stats.py` and rendered by `app/reports/render.py`. The
  model only adds a short narrative (daily, weekly) or "the month in one sentence" and
  recurring themes (monthly), and is given nothing but those computed facts (plus public
  journal excerpts for themes). It is told not to add events, times, feelings or causes.
  If the model is unavailable, reports are produced without prose.
- **Patterns, not causes.** The weekly recap compares sleep after higher- and
  lower-caffeine days; if the difference is at least 30 minutes over 3+ days, it says the
  two *coincided* and that this is a pattern, not a cause.
- **Vault data never appears**: private journal entries, and any record linked to one, are
  excluded from the timeline, every report, and the data the model sees for reports.
- People in reports are listed alphabetically with interaction counts, never ranked.

**Privacy note:** the model sees your messages. With a local model nothing leaves your
machine; a `:cloud` model (such as `nemotron-3-ultra:cloud`) sends conversations to
Ollama's hosted service.

## Sample data

Optional demo data for frontend work (refuses to run when `APP_ENV=production`):

```bash
cd backend && python -m app.db.seed
```

## API

REST under `/api`. Every resource supports `GET` (list, with `date_from`, `date_to`,
`limit`, `offset`), `POST`, `GET /{id}`, `PATCH /{id}` (partial update) and `DELETE /{id}`.

| Resource | Extra |
| --- | --- |
| `POST /api/chat` | `{message, conversation_id?}` → `{conversation_id, reply, actions}` |
| `/api/chat/conversations` | list; `GET /{id}/messages` returns the transcript |
| `/api/people` | `q` name filter; each has `interaction_count` |
| `/api/interactions` | `person_id` filter; includes `person_name` |
| `/api/music` | `q`, `artist`, `person_id`, `emotion`; `GET /top` |
| `/api/subscriptions` | `active` filter; `GET /summary` (monthly and yearly totals per currency) |
| `/api/reminders` | `status` (default pending), `due_before`, `q`; `POST /{id}/complete` |
| `/api/decisions` | `q`, `status`, date range |
| `/api/waiting` | `status` (default waiting), `q`; setting `status` sets `resolved_at` |
| `/api/events` | life events; `q`, `min_importance`, date range |
| `/api/timeline` | `date_from`, `date_to`, `min_importance` |
| `/api/reports/daily` | `GET ?date=` stored recap; `POST {date}` generate |
| `/api/reports/weekly` | `GET ?date=` (any day of the week); `POST {date}` |
| `/api/reports/monthly` | `GET ?year=&month=`; `POST {year, month}` |
| `/api/memories` | list (`min_importance`, `memory_type`), `GET /search?q=`, `PATCH /{id}` (importance), `POST /backfill` |
| `/api/journal` | `q` text search, `min_importance`, `include_private` (private entries are hidden unless set) |
| `/api/expenses` | `category`, `merchant`, `is_impulse`; `GET /summary`, `GET /categories` |
| `/api/moods` | |
| `/api/sleep` | |
| `/api/caffeine` | date filters use local calendar days |

Full schema: http://localhost:8000/docs

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | local `fulyn` DB | SQLAlchemy URL (`postgresql+psycopg://…`) |
| `DEFAULT_TIMEZONE` | `Asia/Colombo` | Used to interpret "today", "last night" and similar |
| `DEFAULT_CURRENCY` | `LKR` | ISO 4217 code for amounts |
| `MAJOR_PURCHASE_AMOUNT` | `10000` | Expenses at or above this (home currency) appear on the timeline |
| `EXPENSE_CATEGORIES` | Food, Cafe, Transport, … Other | JSON list of allowed categories |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama server |
| `OLLAMA_MODEL` | none | Model name. No default on purpose: set it explicitly |
| `OLLAMA_TIMEOUT_SECONDS` | `180` | Per model call |
| `OLLAMA_EMBED_MODEL` | none | Embedding model for semantic search (768 dimensions), e.g. `nomic-embed-text` |
| `EMBED_DOCUMENT_PREFIX` / `EMBED_QUERY_PREFIX` | empty | Task prefixes some embedding models expect |
| `AGENT_MAX_TOOL_ITERATIONS` | `8` | Model rounds per message |
| `AGENT_HISTORY_MESSAGES` | `30` | Earlier chat messages sent as context |
| `BACKEND_URL` | `http://localhost:8000` | Where the frontend proxies `/api/*` |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed origins for direct API calls |

## Privacy

- No analytics, tracking scripts or telemetry (`NEXT_TELEMETRY_DISABLED=1` in Docker).
- Request bodies are never logged. Unhandled errors return a generic 500 and log only
  the exception type and path.
- Secrets live in `.env`, which is git-ignored. Only `.env.example` is committed.
- Postgres, the API and the frontend bind to `127.0.0.1` only.

## Decisions

- **Sync SQLAlchemy + psycopg 3.** Simpler than async for a single-user app; FastAPI runs
  sync endpoints in a thread pool.
- **Next.js rewrites instead of CORS** for browser traffic, so no backend URL is baked
  into client bundles.
- **Money is `NUMERIC(14,2)`** and travels as a string in JSON. Amounts with more than
  two decimal places are rejected rather than rounded.
- **Naive datetimes are local time.** A time without an offset (e.g. from a
  `datetime-local` input) is read in `DEFAULT_TIMEZONE`, never UTC. "Today" defaults are
  also computed in that timezone.
- **Uncertainty is explicit.** Sleep and caffeine logs carry `is_approximate`. A drink
  logged without a time is stored at "now" with `is_approximate = true`. Unknown caffeine
  mg stays `NULL`.
- **Sleep:** `sleep_date` is the day you woke up. Duration is computed from the two times
  when both are given and no duration is supplied; everything except the date is optional.
- **Mood** needs at least one of `score`, `label` or `energy_score`. Labels are free text,
  lowercased.
- **Expense categories** are stored as text and validated against `EXPENSE_CATEGORIES`
  (case-insensitive), so the list can change without a migration. Un-marking an impulse
  purchase clears its `impulse_reason`.
- **People dates are dates.** `first_mentioned_at` / `last_interaction_at` keep the spec's
  names but are calendar dates, since interactions are logged per day.
- **Deleting a journal entry keeps linked records**; their `journal_entry_id` becomes `NULL`.
- **One semantic index.** The spec lists an `embedding` column on journal entries; instead
  all embeddings live in `memories`, which references the journal entry. That avoids
  embedding the same text twice and gives later record types the same search path.
- **No task prefixes by default** for `nomic-embed-text`: in a quick comparison on sample
  entries, unprefixed embeddings separated matches from non-matches better. They are
  configurable.
- **Health endpoint returns 200 even when the DB is down**, with `status: "degraded"`,
  so the UI can show what is wrong. `/api/health/live` never touches the database.
