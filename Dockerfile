# Use official lightweight Python image
FROM python:3.12-slim

# Set environment variables to optimize Python container behavior
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Set working directory
WORKDIR /app

# Install system-level dependencies if required (e.g. sqlite3 for verification/debugging)
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker caching layer
COPY requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files into the container
COPY main.py /app/
COPY frontend/ /app/frontend/
COPY services/ /app/services/

# Expose the port dynamically configured by Cloud Run
EXPOSE 8080

# Start the application using Uvicorn, binding dynamically to $PORT
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
