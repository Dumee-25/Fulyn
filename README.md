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
| 4 | Memory: pgvector embeddings, semantic search, memory table, importance | Next |
| 5–10 | People and music, people and music, personal management, reports, analytics, vault, export | Planned |

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

Agent tests use a scripted fake model, so they are fast and deterministic. Tests against
the real configured model are opt-in:

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
`0003` adds chat conversations.

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
| `EXPENSE_CATEGORIES` | Food, Cafe, Transport, … Other | JSON list of allowed categories |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama server |
| `OLLAMA_MODEL` | none | Model name. No default on purpose: set it explicitly |
| `OLLAMA_TIMEOUT_SECONDS` | `180` | Per model call |
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
- **Deleting a journal entry keeps linked records**; their `journal_entry_id` becomes `NULL`.
- **Embeddings are not stored yet.** The `embedding` column is added in Phase 4 once the
  embedding model (and its dimension) is chosen.
- **Health endpoint returns 200 even when the DB is down**, with `status: "degraded"`,
  so the UI can show what is wrong. `/api/health/live` never touches the database.
