FROM python:3.12-slim
ARG D077_SOURCE_SHA=unknown
LABEL org.opencontainers.image.revision=${D077_SOURCE_SHA} \
      com.secondbrain.test.task=d077-phase1c
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY secondbrain_core ./secondbrain_core
RUN pip install --no-cache-dir . uvicorn
# NAS source directories may be owner-only; make the copied Python package
# readable/traversable by the non-root runtime without changing NAS modes.
RUN chmod -R a+rX /app/secondbrain_core
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "secondbrain_core"]
