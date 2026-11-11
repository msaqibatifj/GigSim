# Hugging Face Spaces (Docker SDK) image: API + built React app + MCP servers (stdio) on one port. Same as infra/docker/web.Dockerfile,
# but port 7860 and a non-root uid 1000 (Spaces requirement). State is SQLite under data/processed and is ephemeral on the free tier.
FROM node:22-slim AS web
WORKDIR /w
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
RUN npx vite build

FROM python:3.12-slim
RUN useradd -m -u 1000 user && pip install --no-cache-dir uv
WORKDIR /home/user/app
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml
COPY --chown=user . .
COPY --chown=user --from=web /w/dist ./apps/web/dist
RUN mkdir -p data/processed && chown -R user /home/user/app
USER user
ENV PYTHONUNBUFFERED=1 MODEL_PROFILE=open COOKIE_SECURE=true FASTEMBED_CACHE_PATH=/home/user/.cache/fastembed
EXPOSE 7860
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
