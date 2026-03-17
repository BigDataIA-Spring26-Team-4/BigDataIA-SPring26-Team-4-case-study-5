# Multi-stage Dockerfile for PE Org-AI-R Platform (FastAPI)
FROM python:3.11-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# ============================================================================
# Builder stage - Install Python dependencies
# ============================================================================
FROM base as builder

COPY pyproject.toml poetry.lock* ./

RUN pip install poetry==1.7.1
RUN poetry config virtualenvs.create false
RUN poetry install --without dev --no-interaction --no-ansi --no-root

# ============================================================================
# Runtime stage
# ============================================================================
FROM base as runtime

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ /app/app/

# Create directories for volume mounts
RUN mkdir -p /app/data /app/results

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
