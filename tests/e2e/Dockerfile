FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        nodejs \
        npm && \
    rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install uv for faster Python package management
RUN pip install uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY mcp_second_brain ./mcp_second_brain
COPY *.md *.py ./

# Install the package and dependencies
RUN uv pip install --system .

# Copy test files
COPY tests/e2e ./tests/e2e

# Install test dependencies
RUN pip install pytest pytest-asyncio anyio pytest-timeout pytest-xdist

# Create a non-root user for running tests
RUN useradd -m -u 1000 tester && \
    chown -R tester:tester /app && \
    chmod -R 755 /app && \
    mkdir -p /tmp && chmod 1777 /tmp

# Create necessary directories for Claude config
RUN mkdir -p /home/tester/.config/claude /home/tester/.config/gcloud

# Copy entrypoint script
COPY --chown=tester:tester tests/e2e/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user
USER tester

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]
CMD ["pytest", "tests/e2e", "-v"]