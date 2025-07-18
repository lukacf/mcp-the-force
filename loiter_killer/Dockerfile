FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY loiter_killer.py .

# Create data directory
RUN mkdir -p /app/data

# Run as non-root user
RUN useradd -m -u 1000 loiter && chown -R loiter:loiter /app
USER loiter

# Environment
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import httpx; exit(0 if httpx.get('http://localhost:9876/health').status_code == 200 else 1)"

# Run the service
CMD ["python", "loiter_killer.py"]