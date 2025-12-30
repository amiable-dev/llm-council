# Railway Deployment

Deploy LLM Council to Railway in under 5 minutes.

## Why Railway?

- **No Cold Starts**: Unlike Render Free tier, Railway instances stay warm
- **Webhook Reliable**: Perfect for n8n and other automation platforms
- **Auto-Deploy**: Deploys automatically when you push to GitHub

## Deploy from GitHub

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/github)

Click the button above, then:

1. **Connect GitHub**: Link your GitHub account if not already connected
2. **Select Repository**: Search for `amiable-dev/llm-council` (or fork it first)
3. **Configure Variables**: Add the required environment variables (see below)
4. **Deploy**: Railway will build and deploy automatically

## Manual Setup

### 1. Fork the Repository (Optional)

Fork [amiable-dev/llm-council](https://github.com/amiable-dev/llm-council) to your GitHub account for customization.

### 2. Create Railway Project

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your forked repository

### 3. Configure Build Settings

Railway will auto-detect the Dockerfile. Verify these settings in Project Settings:

| Setting | Value |
|---------|-------|
| Builder | Dockerfile |
| Dockerfile Path | `deploy/railway/Dockerfile` |
| Root Directory | `/` (repository root) |

### 4. Add Environment Variables

Go to **Variables** tab and add:

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key-here
LLM_COUNCIL_API_TOKEN=your-secure-token-here
```

!!! tip "Generate a Secure Token"
    ```bash
    # Generate a random 32-character token
    openssl rand -hex 16
    ```

### 5. Deploy

Railway will automatically deploy when you push to the configured branch (usually `main`).

Check the deployment logs for any errors. A successful deployment shows:

```
INFO:     Uvicorn running on http://0.0.0.0:PORT
```

## Verify Deployment

### Health Check

```bash
curl https://your-app.railway.app/health
# {"status":"ok","service":"llm-council-local"}
```

### API Test

```bash
curl -X POST https://your-app.railway.app/v1/council/run \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the meaning of life?"}'
```

## Custom Domain

1. Go to **Settings** > **Domains**
2. Click "Generate Domain" or "Add Custom Domain"
3. Configure DNS as instructed

## Scaling

Railway automatically scales based on usage. For high-traffic deployments:

1. Go to **Settings** > **Resources**
2. Adjust CPU and Memory limits
3. Enable horizontal scaling if needed

## Troubleshooting

### Build Fails

Check that your fork has the latest changes:

```bash
git remote add upstream https://github.com/amiable-dev/llm-council.git
git fetch upstream
git merge upstream/master
git push
```

### Health Check Fails

1. Verify `PORT` environment variable is not manually set (Railway provides it)
2. Check deployment logs for startup errors
3. Ensure `OPENROUTER_API_KEY` is set correctly

### API Returns 401

Verify your `Authorization` header:

```bash
# Correct format
Authorization: Bearer your-token-here
```

## Cost Estimate

| Usage Level | Monthly Cost |
|-------------|--------------|
| Light (< 100 queries/day) | ~$5 |
| Medium (100-500 queries/day) | ~$10-20 |
| Heavy (500+ queries/day) | $20+ |

Railway bills based on actual usage (CPU, memory, network).

## Next Steps

- [n8n Integration](../integrations/n8n.md) - Connect to workflow automation
- [HTTP API Reference](../guides/http-api.md) - Full API documentation
