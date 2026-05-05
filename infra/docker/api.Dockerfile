FROM python:3.11-slim

WORKDIR /app

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[api]"

# Copy application code
COPY apps/api ./apps/api
COPY packages/ingest/courses.yaml ./packages/ingest/courses.yaml

EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
