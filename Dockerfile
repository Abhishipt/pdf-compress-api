# ==========================================================
# Stage 1 — Builder: install dependencies cleanly
# ==========================================================
FROM python:3.11-slim AS builder

# Avoid Python bytecode & buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system deps only for build stage
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirement list first (better caching)
COPY requirements.txt .

# Install dependencies into /install (isolated)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt --target=/install

# ==========================================================
# Stage 2 — Final lightweight runtime image
# ==========================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy only installed deps and app source
COPY --from=builder /install /usr/local/lib/python3.11/site-packages
COPY . /app

# Expose port for Render
EXPOSE 5000

# Health check (optional but good for Render)
HEALTHCHECK CMD curl --fail http://localhost:5000/ping || exit 1

# Start Flask app with Gunicorn (2 workers = optimal for Render free tier)
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120"]
