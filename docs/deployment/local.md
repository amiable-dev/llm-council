# Local Docker Deployment

Run LLM Council locally using Docker Compose for development and testing.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0+)
- OpenRouter API key

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/amiable-dev/llm-council.git
cd llm-council
```

### 2. Create Environment File

```bash
# Create .env file with your credentials
cat > .env << EOF
OPENROUTER_API_KEY=sk-or-v1-your-key-here
LLM_COUNCIL_API_TOKEN=my-local-dev-token
EOF
```

!!! warning "Security"
    Never commit `.env` to version control. It's already in `.gitignore`.

### 3. Start the Server

```bash
docker compose up --build
```

You should see:

```
llm-council-1  | INFO:     Uvicorn running on http://0.0.0.0:8000
llm-council-1  | INFO:     Application startup complete.
```

### 4. Test the API

```bash
# Health check (no auth required)
curl http://localhost:8000/health

# API request (auth required)
curl -X POST http://localhost:8000/v1/council/run \
  -H "Authorization: Bearer my-local-dev-token" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the best way to learn programming?"}'
```

## Docker Compose Configuration

The `docker-compose.yml` in the repository root:

```yaml
version: '3.8'

services:
  llm-council:
    build:
      context: .
      dockerfile: deploy/railway/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - LLM_COUNCIL_API_TOKEN=${LLM_COUNCIL_API_TOKEN}
      - PORT=8000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      start_period: 10s
      retries: 3
    restart: unless-stopped
```

## Common Commands

```bash
# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop the server
docker compose down

# Rebuild after code changes
docker compose up --build

# Clean rebuild (removes cache)
docker compose build --no-cache
```

## Development Workflow

### Hot Reload (Development Mode)

For development, mount your source code as a volume:

```yaml
# docker-compose.override.yml (create this file)
version: '3.8'
services:
  llm-council:
    volumes:
      - ./src:/app/src:ro
    command: ["sh", "-c", "pip install -e '.[http]' && llm-council serve --host 0.0.0.0 --port 8000 --reload"]
```

Then:

```bash
docker compose up
```

Changes to source code will auto-reload the server.

### Running Without Docker

For faster iteration during development:

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with HTTP support
pip install -e ".[http]"

# Set environment variables
export OPENROUTER_API_KEY=sk-or-v1-...
export LLM_COUNCIL_API_TOKEN=dev-token

# Run the server
llm-council serve --host 0.0.0.0 --port 8000 --reload
```

## Connecting to n8n

If running n8n locally with Docker:

```yaml
# docker-compose.override.yml
version: '3.8'
services:
  n8n:
    image: n8nio/n8n
    ports:
      - "5678:5678"
    environment:
      - N8N_HOST=localhost
    volumes:
      - n8n_data:/home/node/.n8n

volumes:
  n8n_data:
```

In n8n workflows, use `http://llm-council:8000` as the council URL (Docker service name).

## Troubleshooting

### Port Already in Use

```bash
# Find what's using port 8000
lsof -i :8000

# Kill the process or use a different port
docker compose up -e PORT=8001
```

### Build Fails

```bash
# Clean Docker cache
docker system prune -f
docker compose build --no-cache
```

### Container Exits Immediately

Check logs for errors:

```bash
docker compose logs llm-council
```

Common issues:
- Missing `OPENROUTER_API_KEY`
- Invalid API key format
- Port conflict

### Permission Denied

On Linux, you may need to run Docker with sudo or add your user to the docker group:

```bash
sudo usermod -aG docker $USER
# Log out and back in
```

## Next Steps

- [HTTP API Reference](../guides/http-api.md) - Full API documentation
- [n8n Integration](../integrations/n8n.md) - Workflow automation setup
- [Railway Deployment](railway.md) - Deploy to production
