# Use official Python image
FROM python:3.10-slim

# Install Ghostscript
RUN apt-get update && apt-get install -y ghostscript

# Set working directory
WORKDIR /app

# Copy app files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port
EXPOSE 10000

# Run the app
CMD exec gunicorn --bind 0.0.0.0:10000 app:app
