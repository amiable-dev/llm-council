# From Clone to Cloud in 60 Seconds: One-Click LLM Council Deployment

*Published: December 2025*

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
| **Railway** | [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/llm-council?referralCode=amiable-dev) | ~$5/mo |
| **Render** | [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/amiable-dev/llm-council) | Free tier |

Click the button. Add your API keys. Done.

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
curl -X POST https://your-council.railway.app/v1/council/run \
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

   [![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/llm-council?referralCode=amiable-dev)

2. **Configure Environment Variables**

   Railway will prompt you for:

   | Variable | Description |
   |----------|-------------|
   | `OPENROUTER_API_KEY` | Your OpenRouter API key |
   | `LLM_COUNCIL_API_TOKEN` | A secure token for API auth |

   Generate a secure token:
   ```bash
   openssl rand -hex 16
   ```

3. **Deploy**

   Railway builds and deploys automatically. Within 2-3 minutes, you'll have a live URL.

4. **Test Your Deployment**

   ```bash
   # Health check
   curl https://your-app.railway.app/health

   # API request
   curl -X POST https://your-app.railway.app/v1/council/run \
     -H "Authorization: Bearer your-token" \
     -H "Content-Type: application/json" \
     -d '{"prompt": "What is the capital of France?"}'
   ```

## n8n Integration

With a deployed council endpoint, n8n integration is straightforward. Add an HTTP Request node with these settings:

| Setting | Value |
|---------|-------|
| **Method** | POST |
| **URL** | `https://your-council.railway.app/v1/council/run` |
| **Authentication** | Header Auth |
| **Header Name** | Authorization |
| **Header Value** | `Bearer {{$env.COUNCIL_TOKEN}}` |
| **Body** | JSON |

**Request Body:**
```json
{
  "prompt": "{{$json.question}}",
  "verdict_type": "binary"
}
```

Store your `COUNCIL_TOKEN` in n8n credentials, not in the workflow JSON.

See the [full n8n integration guide](../integrations/n8n.md) for complete workflow examples including code review automation and support ticket triage.

## Revenue Sustainability

Why Railway as the primary platform? Beyond technical fit, Railway's Open Source Kickback program provides up to 25% revenue sharing for template creators. This creates a sustainability path for open-source projects.

When you deploy via our template, a portion of your Railway spend supports LLM Council development. Thank you for contributing to open-source sustainability.

## What's Next?

- [Deployment Guide](../deployment/index.md) - Detailed platform-specific guides
- [n8n Integration](../integrations/n8n.md) - Workflow automation setup
- [HTTP API Reference](../guides/http-api.md) - Full API documentation
- [ADR-038](../adr/ADR-038-one-click-deployment-strategy.md) - Technical decision record

---

*This post implements [ADR-038: One-Click Deployment Strategy](../adr/ADR-038-one-click-deployment-strategy.md).*

*Explore the source code: [github.com/amiable-dev/llm-council](https://github.com/amiable-dev/llm-council)*
