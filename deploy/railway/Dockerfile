# LLM Council Production Dockerfile
# Optimized for Railway, Render, and local Docker Compose deployment
#
# Build: docker build -f deploy/railway/Dockerfile -t llm-council .
# Run:   docker run -p 8000:8000 -e OPENROUTER_API_KEY=sk-... -e LLM_COUNCIL_API_TOKEN=... llm-council

FROM python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7

# Set working directory
WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install the [http] dependencies first, at the exact versions and hashes in
# uv.lock. deploy/railway/requirements.txt is exported from the lockfile;
# tests/test_pinned_requirements.py fails when the two drift apart.
COPY deploy/railway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Version for setuptools-scm (hatch-vcs requires git metadata, which isn't available in Docker)
# This can be overridden at build time: docker build --build-arg VERSION=0.19.0 ...
ARG VERSION=0.0.0.dev0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}

# Install the package itself; its dependencies are already in place.
# Editable (-e) so the install runs from /app/src: OpenSSF Scorecard accepts a
# local install as pinned only in the form `--no-deps -e`.
RUN pip install --no-cache-dir --no-deps -e .

# Create non-root user for security (ADR-038 requirement)
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Default port (can be overridden by $PORT env var)
ENV PORT=8000
EXPOSE $PORT

# Health check for container orchestrators
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Start the server
# Note: $PORT is provided by Railway/Render at runtime
CMD ["sh", "-c", "llm-council serve --host 0.0.0.0 --port ${PORT:-8000}"]
