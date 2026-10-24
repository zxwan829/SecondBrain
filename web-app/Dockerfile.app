FROM node:22-alpine AS frontend-build
WORKDIR /build
ARG VITE_ENABLE_NOTES=false
COPY secondbrain-frontend/package.json secondbrain-frontend/package-lock.json ./
RUN npm ci
COPY secondbrain-frontend/ ./
RUN npm run typecheck && VITE_ENABLE_NOTES=${VITE_ENABLE_NOTES} npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SB_STATIC_ROOT=/app/static TMPDIR=/tmp
# Match the verified App/Core data and secret owner on the NAS. Other hosts can
# override these at runtime with their own least-privilege UID/GID.
ARG SB_APP_UID=1026
ARG SB_APP_GID=100
ARG SB_SOURCE_REVISION=unknown
LABEL org.opencontainers.image.revision=${SB_SOURCE_REVISION}
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /tmp \
    && chmod 1777 /tmp
WORKDIR /app
COPY secondbrain-core/pyproject.toml secondbrain-core/README.md ./
COPY secondbrain-core/secondbrain_core ./secondbrain_core
COPY --from=frontend-build /build/dist ./static
RUN pip install --no-cache-dir . uvicorn && chmod -R a+rX /app/secondbrain_core /app/static
USER ${SB_APP_UID}:${SB_APP_GID}
EXPOSE 8000
CMD ["python", "-m", "secondbrain_core"]
