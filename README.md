# OpenNow

OpenNow runs its full local development stack behind one Caddy origin. The stack
contains the Next.js web app, Django API, Celery worker and beat scheduler,
PostgreSQL with PostGIS, Redis, and Caddy.

## Start the stack

Start every service from a fresh clone:

```bash
docker compose up --build
```

The defaults are for local development. Copy `.env.example` to `.env` when you
want to override them.

Open <http://localhost:8080>. Caddy serves the web app and forwards `/api/*` to
Django. The public health response is available at
<http://localhost:8080/api/health>, and its OpenAPI schema is available at
<http://localhost:8080/api/schema/>.

## Run checks locally

Backend checks use the Python environment locked in `backend/uv.lock` and expect
a PostgreSQL database with the PostGIS extension:

```bash
cd backend
uv sync
uv run ruff check .
uv run pytest --cov=core --cov-branch --cov-fail-under=80
```

Web checks use the lockfile in `web/`:

```bash
cd web
pnpm install --frozen-lockfile
pnpm run generate:api
pnpm run lint
pnpm run typecheck
pnpm exec vitest run --coverage
pnpm run build
```

The generated client types live at `web/src/api/schema.d.ts`; regenerate them
after changing `backend/openapi.yaml`.
