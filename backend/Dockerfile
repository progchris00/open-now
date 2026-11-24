FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgdal36 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app \
    && useradd --system --gid app --create-home app

COPY --from=ghcr.io/astral-sh/uv:0.11.9 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY --chown=app:app . .
RUN chown app:app /app

USER app
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
