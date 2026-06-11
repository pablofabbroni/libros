FROM python:3.11-slim

# Install system dependencies if any are needed (none for PyMuPDF, but general build-essential is good to have)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app /app

# Expose server port
EXPOSE 8000

# Set environment defaults
ENV BOOKS_DIR=/app/books
ENV DB_PATH=/app/data/stats.db
ENV DOWNLOAD_LIMIT_DAILY=10
ENV ADMIN_PASSWORD=admin123
ENV PORT=8000

# Run the server
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
