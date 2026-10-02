FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra semantic --no-install-project
RUN uv pip install --system --no-cache-dir ".[semantic]"

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /usr/local /usr/local
COPY src ./src
COPY web ./web
USER 65532:65532
EXPOSE 8000
CMD ["findex", "serve", "--port", "8000"]
