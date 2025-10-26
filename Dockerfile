# Use stable and lightweight Python image
FROM python:3.10.14-slim

# Prevent Python from writing .pyc files and buffering output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install Ghostscript (for PDF compression)
RUN apt-get update && apt-get install -y --no-install-recommends ghostscript \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose Flask/Gunicorn port
EXPOSE 5000

# Optional health check
HEALTHCHECK CMD curl --fail http://localhost:5000/ping || exit 1

# Run Gunicorn server
CMD exec gunicorn --bind 0.0.0.0:5000 --workers 1 --timeout 300 app:app

