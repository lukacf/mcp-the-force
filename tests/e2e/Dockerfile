FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install project in editable mode with test dependencies
RUN uv pip install -e ".[test]"

# Create non-root user for security
RUN useradd -m -u 1000 mcp && chown -R mcp:mcp /app
USER mcp

# Expose MCP server port
EXPOSE 8000

# Default command runs the tests
CMD ["pytest", "-xvs", "-m", "e2e", "tests/e2e/"]