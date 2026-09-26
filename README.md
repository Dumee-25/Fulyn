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
| 2 | Core life logging (journal, expenses, mood, sleep, caffeine) | Next |
| 3–10 | Agent, memory, people and music, personal management, reports, analytics, vault, export | Planned |

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, Pydantic v2, Alembic, psycopg 3
- **Database:** PostgreSQL 17 with pgvector
- **AI (from Phase 3):** Ollama, configured through `OLLAMA_BASE_URL` and `OLLAMA_MODEL`
- **Frontend:** Next.js 16 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui

## Layout

```text
backend/
  app/
    api/        # routers (thin: no domain logic)
    agent/      # agent loop and prompts (Phase 3)
    core/       # settings, logging
    db/         # engine, session, declarative base and mixins
    models/     # ORM models (import them in models/__init__.py for Alembic)
    schemas/    # Pydantic request/response schemas
    services/   # domain logic
    tools/      # agent tool definitions (Phase 3)
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
bind-mounted, so both servers reload when you edit code.

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

The Next.js server proxies every `/api/*` request to `BACKEND_URL`
(default `http://localhost:8000`), so the browser only ever talks to one origin.

## Tests and linting

```bash
cd backend && pytest && ruff check . && ruff format --check .
```

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

## Migrations

```bash
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Revision `0001` enables the `vector` extension.

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | local `fulyn` DB | SQLAlchemy URL (`postgresql+psycopg://…`) |
| `DEFAULT_TIMEZONE` | `Asia/Colombo` | Used to interpret "today", "last night" and similar |
| `DEFAULT_CURRENCY` | `LKR` | ISO 4217 code for amounts |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | none | Model name. No default on purpose: set it explicitly |
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
- **Health endpoint returns 200 even when the DB is down**, with `status: "degraded"`,
  so the UI can show what is wrong. `/api/health/live` never touches the database.
