# OpenNow

OpenNow runs its local development stack behind one Caddy origin. The stack
contains the Next.js web app, Django API, Celery worker and beat scheduler,
PostgreSQL with PostGIS, Redis, and Caddy.

## Start the stack

From a fresh clone, start all seven services:

```bash
docker compose up --build
```

Open <http://localhost:8080>. Caddy serves the web app and forwards `/api/*`
to Django. The public health endpoint is available at
<http://localhost:8080/api/health>, and the generated schema is available at
<http://localhost:8080/api/schema/>.

Copy `.env.example` to `.env` to override the local defaults.

## Run backend checks

Start the database first, then run the checks from the repository root:

```bash
docker compose up -d db redis
uv run --project backend ruff check backend
uv run --project backend pytest --cov=backend/core --cov-branch --cov-fail-under=80
uv run --project backend pytest backend/pricing/tests --cov=backend/pricing --cov-branch --cov-fail-under=80
```

## Run web checks

```bash
cd web
pnpm install --frozen-lockfile
pnpm run generate:api
pnpm run lint
pnpm run typecheck
pnpm exec vitest run --coverage
pnpm run build
```
