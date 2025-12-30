# Render Deployment

Deploy LLM Council to Render with the free tier for evaluation, or paid tier for production.

## Important: Free Tier Limitations

!!! warning "Cold Start Warning"
    Render Free tier **spins down after 15 minutes of inactivity**. This causes:

    - 30-60 second cold starts
    - Potential webhook timeouts (n8n, Make, Zapier)
    - Unreliable for production use

    **For webhook integrations, use [Railway](railway.md) or Render paid tier.**

## One-Click Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/amiable-dev/llm-council)

## Manual Setup

### 1. Fork the Repository

Fork [amiable-dev/llm-council](https://github.com/amiable-dev/llm-council) to your GitHub account.

### 2. Create New Web Service

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New" > "Web Service"
3. Connect your forked repository

### 3. Configure Build Settings

| Setting | Value |
|---------|-------|
| Name | `llm-council` |
| Environment | Docker |
| Dockerfile Path | `deploy/railway/Dockerfile` |
| Instance Type | Free (evaluation) or Starter ($7/mo) |

### 4. Add Environment Variables

In the **Environment** section, add:

| Key | Value |
|-----|-------|
| `OPENROUTER_API_KEY` | Your OpenRouter API key |
| `LLM_COUNCIL_API_TOKEN` | Your secure API token |

!!! tip "Generate a Secure Token"
    ```bash
    openssl rand -hex 16
    ```

### 5. Configure Health Check

Render auto-detects from `render.yaml`, but verify:

| Setting | Value |
|---------|-------|
| Health Check Path | `/health` |

### 6. Deploy

Click "Create Web Service". Render will build and deploy your instance.

## Blueprint Deployment

Alternatively, use the included `render.yaml` blueprint:

1. Fork the repository
2. Go to Render Dashboard > "New" > "Blueprint"
3. Select your forked repo
4. Render will read `render.yaml` and configure automatically

```yaml
# render.yaml (already in repo)
services:
  - type: web
    name: llm-council
    runtime: docker
    dockerfilePath: deploy/railway/Dockerfile
    healthCheckPath: /health
    autoDeploy: false
```

## Verify Deployment

### Health Check

```bash
curl https://your-app.onrender.com/health
# {"status":"ok","service":"llm-council-local"}
```

!!! note "First Request Cold Start"
    If the service is cold, the first request may take 30-60 seconds.

### API Test

```bash
curl -X POST https://your-app.onrender.com/v1/council/run \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?"}'
```

## Keeping Service Warm

For Free tier with webhook needs, consider these workarounds:

### Option 1: External Ping Service

Use a free uptime monitor to ping `/health` every 10 minutes:

- [UptimeRobot](https://uptimerobot.com/) (free, 5-min intervals)
- [Freshping](https://www.freshworks.com/website-monitoring/) (free, 1-min intervals)

### Option 2: Scheduled Cron Job

Add a GitHub Action to ping your service:

```yaml
# .github/workflows/keep-warm.yml
name: Keep Render Warm
on:
  schedule:
    - cron: '*/10 * * * *'  # Every 10 minutes
jobs:
  ping:
    runs-on: ubuntu-latest
    steps:
      - run: curl -f ${{ secrets.RENDER_URL }}/health
```

### Option 3: Upgrade to Paid Tier

For $7/mo, Render Starter tier eliminates cold starts.

## Troubleshooting

### Build Fails

Check Dockerfile path is correct: `deploy/railway/Dockerfile`

### Service Never Starts

1. Check deployment logs for errors
2. Verify `OPENROUTER_API_KEY` is set
3. Ensure Dockerfile builds locally:
   ```bash
   docker build -f deploy/railway/Dockerfile -t llm-council-test .
   ```

### Webhooks Timeout

This is the cold start problem. Solutions:

1. Switch to [Railway](railway.md) (recommended)
2. Upgrade to Render paid tier
3. Use keep-warm ping service

## Cost Comparison

| Tier | Monthly Cost | Cold Starts | Webhook Ready |
|------|--------------|-------------|---------------|
| Free | $0 | Yes (15min) | No |
| Starter | $7 | No | Yes |
| Standard | $25 | No | Yes |

## Next Steps

- [HTTP API Reference](../guides/http-api.md) - Full API documentation
- [Railway Deployment](railway.md) - Alternative without cold starts
