# ── DataViz Pro — Flask Production Image ───────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p uploads reports ml_models_storage saved_projects instance logs app/static/reports

# Expose port
EXPOSE 5000

# Non-root user for security
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Production WSGI server
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:5000", "--timeout", "120", "app:create_app('production')"]
