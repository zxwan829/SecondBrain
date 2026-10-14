FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY secondbrain-frontend/package.json secondbrain-frontend/package-lock.json ./
RUN npm ci
COPY secondbrain-frontend/ ./
RUN npm run typecheck && npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SB_STATIC_ROOT=/app/static
WORKDIR /app
COPY secondbrain-core/pyproject.toml secondbrain-core/README.md ./
COPY secondbrain-core/secondbrain_core ./secondbrain_core
COPY --from=frontend-build /build/dist ./static
RUN pip install --no-cache-dir . uvicorn && chmod -R a+rX /app/secondbrain_core /app/static
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "secondbrain_core"]
