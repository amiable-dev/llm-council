# Deployment

Deploy LLM Council to the cloud in under 5 minutes with one-click deployment, or run locally with Docker Compose.

## Quick Deploy

| Platform | Deploy | Best For |
|----------|--------|----------|
| **Railway** | [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/github) | Production use, webhook integrations |
| **Render** | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/amiable-dev/llm-council) | Evaluation, free tier testing |

!!! warning "Render Cold Start"
    Render Free tier spins down after 15 minutes of inactivity. This causes 30-60 second cold starts that may timeout n8n webhooks. For reliable webhook integration, use Railway or Render paid tier.

## Platform Comparison

| Feature | Railway | Render Free | Render Paid |
|---------|---------|-------------|-------------|
| **Cold Start** | None | 30-60s after 15min idle | None |
| **Free Tier** | $5/mo trial | 750 hrs/mo | $7/mo+ |
| **Webhook Ready** | Yes | No (timeout risk) | Yes |
| **Auto-scaling** | Yes | No | Yes |

## Deployment Options

<div class="grid cards" markdown>

-   :material-train: **[Railway](railway.md)**

    ---

    Recommended for production. No cold starts, template marketplace discovery, and webhook reliability.

-   :material-palette: **[Render](render.md)**

    ---

    Free tier for evaluation. Great for testing before committing to a paid plan.

-   :material-docker: **[Local Docker](local.md)**

    ---

    Run locally with Docker Compose. Perfect for development and testing.

</div>

## Required Configuration

All deployment options require these environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | **Yes** | Your OpenRouter API key for LLM calls |
| `LLM_COUNCIL_API_TOKEN` | **Yes** | Bearer token for API authentication |
| `PORT` | No | Server port (default: 8000) |

!!! danger "Security Notice"
    Never commit API keys to your repository. Use platform secrets management:

    - **Railway**: Project Settings > Variables
    - **Render**: Service > Environment
    - **Local**: `.env` file (gitignored)

## Verify Deployment

After deployment, verify your instance is running:

```bash
# Health check (no auth required)
curl https://your-instance.railway.app/health

# Test API (requires auth)
curl -X POST https://your-instance.railway.app/v1/council/run \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 2+2?"}'
```

## Next Steps

- [HTTP API Reference](../guides/http-api.md) - Full API documentation
- [n8n Integration](../integrations/n8n.md) - Workflow automation
- [Configuration Guide](../getting-started/configuration.md) - Customize your council
