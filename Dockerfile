FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder
WORKDIR /app
ENV HF_HOME=/opt/huggingface
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY web ./web
RUN uv sync --frozen --no-dev --extra semantic --no-install-project
RUN uv pip install --system --no-cache-dir ".[semantic]"
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
RUN findex embed web/demo_docs.jsonl --output web/demo_embeddings.npy --metadata web/demo_embeddings.json

FROM python:3.13-slim-bookworm
ENV HF_HOME=/opt/huggingface PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /usr/local /usr/local
COPY --from=builder /opt/huggingface /opt/huggingface
COPY src ./src
COPY web ./web
USER 65532:65532
EXPOSE 8000
CMD ["findex", "serve", "--port", "8000"]
