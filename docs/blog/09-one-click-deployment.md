# From Clone to Cloud in 60 Seconds: One-Click LLM Council Deployment

*Published: December 2025*

## Prerequisites

Before deploying, you'll need:

- An [OpenRouter account](https://openrouter.ai) with API key
- A Railway or Render account (free to create)
- For local development: Docker Desktop installed

## The Problem

You want to try LLM Council. You read the documentation, you understand the 3-stage deliberation process. Now you want to run it.

The traditional path looks like this:

```bash
git clone https://github.com/amiable-dev/llm-council.git
cd llm-council
pip install -e ".[http]"
export OPENROUTER_API_KEY=sk-or-v1-...
llm-council serve
```

Not bad for developers. But what about:

- **n8n users** who want to integrate with workflow automation?
- **Evaluators** who want to test before committing to a tech stack?
- **Teams** who need a shared council endpoint without everyone managing API keys?

For these users, deployment friction is the #1 barrier to adoption.

## The Solution: One-Click Deploy

With [ADR-038](../adr/ADR-038-one-click-deployment-strategy.md) (our Architectural Decision Record for deployment strategy), we've added one-click deployment to two platforms:

| Platform | Deploy | Cost |
|----------|--------|------|
| **Railway** | [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/llm-council?referralCode=K9dsYj) | ~$5/mo |
| **Render** | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/amiable-dev/llm-council) | Free tier |

Click the button, select the repository, add your API keys (`OPENROUTER_API_KEY` and `LLM_COUNCIL_API_TOKEN`). Done.

## Why Two Platforms?

Different users have different needs:

### Railway: For Production

Railway is our recommended platform for production use:

- **No cold starts** - Paid Railway instances stay warm (unlike free tier platforms)
- **Webhook reliability** - Critical for n8n/Make/Zapier integration
- **Template marketplace** - Organic discovery among 2M+ developers
- **Revenue sharing** - Railway shares template revenue with creators, supporting open-source sustainability

### Render: For Evaluation

Render's free tier is perfect for evaluation:

- **750 free hours/month** - Plenty for testing
- **Quick setup** - No credit card required
- **Blueprint support** - Infrastructure-as-code

**Caveat**: Render Free tier spins down after 15 minutes of inactivity. This causes 30-60 second cold starts that will likely timeout webhooks (n8n/Zapier default timeout is often 30 seconds). For workflow automation integration, use Railway or Render paid tier.

## Security First: API Token Authentication

A public council endpoint without authentication is a credit-draining vulnerability. With ADR-038, we've added `LLM_COUNCIL_API_TOKEN` authentication:

```bash
# Set in your deployment platform's environment
LLM_COUNCIL_API_TOKEN=your-secure-token-here
```

All protected endpoints now require a Bearer token:

```bash
curl -X POST https://your-app.railway.app/v1/council/run \
  -H "Authorization: Bearer your-secure-token-here" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the best way to learn programming?"}'
```

The `/health` endpoint remains public for load balancer health checks.

## Local Development with Docker Compose

For local testing and development:

```bash
# Clone the repo
git clone https://github.com/amiable-dev/llm-council.git
cd llm-council

# Create .env file
echo "OPENROUTER_API_KEY=sk-or-v1-..." > .env
echo "LLM_COUNCIL_API_TOKEN=my-local-token" >> .env

# Start the server
docker compose up --build
```

The council is now running at `http://localhost:8000`.

## Step-by-Step: Railway Deployment

1. **Click Deploy on Railway**

   [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/llm-council?referralCode=K9dsYj)

2. **Connect GitHub (if prompted)**

   - The template deploys from `amiable-dev/llm-council` automatically
   - Connect your GitHub account if Railway prompts you

3. **Configure Environment Variables**

   Railway will prompt you for:

   | Variable | Description |
   |----------|-------------|
   | `OPENROUTER_API_KEY` | Your OpenRouter API key |
   | `LLM_COUNCIL_API_TOKEN` | A secure token for API auth |

   Generate a secure token:
   ```bash
   openssl rand -hex 16
   ```

4. **Deploy**

   Railway builds and deploys automatically. Within 2-3 minutes, you'll have a live URL.

5. **Test Your Deployment**

   ```bash
   # Health check (no auth required)
   curl https://your-app.railway.app/health
   # Expected: {"status":"ok","service":"llm-council-local"}

   # API request (auth required)
   curl -X POST https://your-app.railway.app/v1/council/run \
     -H "Authorization: Bearer your-token" \
     -H "Content-Type: application/json" \
     -d '{"prompt": "What is the capital of France?"}'
   ```

   A successful response returns the 3-stage deliberation results plus metadata:
   ```json
   {
     "stage1": [{"model": "...", "content": "..."}],
     "stage2": [{"model": "...", "evaluation": "...", "parsed_ranking": [...]}],
     "stage3": {"synthesis": "Paris is the capital of France..."},
     "metadata": {
       "aggregate_rankings": {"Response A": 1.5, "Response B": 2.0},
       "config": {"council_size": 3, "verdict_type": "synthesis"}
     }
   }
   ```

## Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| **401 Unauthorized** | Missing or incorrect token | Verify `Authorization: Bearer <token>` header format |
| **500 Internal Server Error** | Invalid OpenRouter API key | Check `OPENROUTER_API_KEY` is set correctly |
| **502 Bad Gateway** | App crashed on startup | Check deployment logs for errors |
| **Timeout on first request** | Cold start (Render free tier) | Wait 60s and retry, or use Railway |
| **Health check fails** | Port binding issue | Ensure app binds to `$PORT` (handled automatically) |

## n8n Integration

With a deployed council endpoint, n8n integration is straightforward. In your n8n workflow, add an **HTTP Request** node with these settings:

| Setting | Value |
|---------|-------|
| **Method** | POST |
| **URL** | `https://your-app.railway.app/v1/council/run` |
| **Authentication** | Header Auth |
| **Header Name** | Authorization |
| **Header Value** | `Bearer your-token-here` |
| **Body** | JSON |

**Request Body:**
```json
{
  "prompt": "{{$json.question}}",
  "verdict_type": "binary"
}
```

!!! tip "Secure Token Storage"
    Store your API token in n8n environment variables (`Settings → Variables`) as `COUNCIL_TOKEN`, then reference it as `{{$env.COUNCIL_TOKEN}}` in the Header Value field.

!!! note "Input Field"
    The `{{$json.question}}` syntax assumes the previous node outputs a JSON field named `question`. Adjust to match your workflow trigger.

See the [full n8n integration guide](../integrations/n8n.md) for complete workflow examples including code review automation and support ticket triage.

## Revenue Sustainability

Why Railway as the primary platform? Beyond technical fit, Railway's [Open Source Kickback program](https://blog.railway.com/p/1M-open-source-kickbacks) provides revenue sharing for template creators. This creates a sustainability path for open-source projects.

By using our [official Railway template](https://railway.com/deploy/llm-council?referralCode=K9dsYj), a portion of your Railway spend supports LLM Council development.

## What's Next?

- [Deployment Guide](../deployment/index.md) - Detailed platform-specific guides
- [n8n Integration](../integrations/n8n.md) - Workflow automation setup
- [HTTP API Reference](../guides/http-api.md) - Full API documentation
- [ADR-038](../adr/ADR-038-one-click-deployment-strategy.md) - Technical decision record

---

*This post implements [ADR-038: One-Click Deployment Strategy](../adr/ADR-038-one-click-deployment-strategy.md).*

*Explore the source code: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
