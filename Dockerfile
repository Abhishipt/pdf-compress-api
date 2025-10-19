# ==========================================================
# Stage 1 — Build environment
# ==========================================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Ghostscript and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ghostscript \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install Python dependencies to /install
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt --target=/install

# ==========================================================
# Stage 2 — Runtime environment
# ==========================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Ghostscript & curl again for runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependencies and app source
COPY --from=builder /install /usr/local/lib/python3.11/site-packages
COPY . /app

# Expose port
EXPOSE 5000

# Health check (Render will auto-restart if unhealthy)
HEALTHCHECK CMD curl --fail http://localhost:5000/ping || exit 1

# Start Gunicorn (2 workers for Render Free Tier)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
