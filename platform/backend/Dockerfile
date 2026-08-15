FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm

RUN groupadd --system --gid 10001 bearvoice \
    && useradd --system --uid 10001 --gid bearvoice --home-dir /nonexistent bearvoice
WORKDIR /app
COPY --from=builder --chown=bearvoice:bearvoice /app/.venv /app/.venv
COPY --from=builder --chown=bearvoice:bearvoice /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=bearvoice:bearvoice /app/alembic /app/alembic
ENV PATH="/app/.venv/bin:${PATH}"
USER bearvoice
EXPOSE 8000
CMD ["uvicorn", "bearvoice.main:app", "--host", "0.0.0.0", "--port", "8000"]
