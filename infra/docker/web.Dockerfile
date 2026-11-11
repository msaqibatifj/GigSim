# Builds the web app, then the API image serves apps/web/dist (one public URL).
FROM node:22-slim AS web
WORKDIR /w
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
RUN npx vite build

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml
COPY . .
COPY --from=web /w/dist ./apps/web/dist
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
