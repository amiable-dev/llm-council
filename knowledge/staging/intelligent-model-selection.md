# Auto Router - Intelligent Model Selection

**Source:** https://openrouter.ai/docs/guides/routing/routers/auto-router
**Added:** 2026-08-23
**Tags:** #unsorted

---

> Automatically select the best AI model for your prompts using OpenRouter's Auto Router, powered by the wisdom of the market.

---

The Auto Router automatically selects the best model for your prompt. It is powered by the market: the aggregate spend of millions of people using OpenRouter, measured over a trailing 7-day window for each task type. Think of it like a market index that stays up to date and gets more efficient as more people use OpenRouter. See [How It Works](#how-it-works) and the [Cost Tier](#cost-tier) settings. Two slugs run this router:

-   **[Auto](https://openrouter.ai/openrouter/auto)** (`openrouter/auto`) — works like any other model slug; sending it as the `model` is all you need to do.
-   **[Auto Beta](https://openrouter.ai/openrouter/auto-beta)** (`openrouter/auto-beta`) — the early-access track. New routing behaviors land here before they reach `openrouter/auto`. Everything on this page applies to it too, except that per-request settings must use the plugin id `auto-beta-router` instead of `auto-router`:

## Overview

Instead of manually choosing a model, let the Auto Router analyze your prompt and select a model based on what the OpenRouter community, in aggregate, uses for that kind of work. The router considers factors like task type, model capabilities, tool support, and cost.

## How It Works

The Auto Router routes on the wisdom of the market: what millions of people, in aggregate, spend on for exactly the kind of task your prompt represents. The rankings are computed from aggregate anonymized spend statistics. Prompts are classified in-flight without requiring retention.

1.  **Classify the task.** A fast, lightweight classifier assigns each prompt one of ~30 fine-grained task types — for example `code:debugging`, `agent:multi_step_planning`, `qa_knowledge`, `math`, `customer_support`, or `research_report`.
2.  **Rank by real-world spend share.** For that task type, the router looks up which models the OpenRouter community actually spends on over a trailing 7-day window — the “Share of Spend” view from the [task-spend rankings](https://openrouter.ai/rankings#task-spend). This is a live signal: when developers migrate a workload to a new model, the router follows within days, with no retraining or manual curation.
3.  **Apply your cost tier.** The [`cost_tier`](#cost-tier) setting selects a cost band: `low`, `medium`, `high`, `xhigh`, or `max`.
4.  **Route with fallbacks.** The top surviving models (in market spend-share order) become the primary pick plus fallbacks, after honoring your account-level model and provider restrictions, guardrails, ZDR policies, `allowed_models` restrictions, and output-modality requirements. If classification or rankings are ever unavailable, the router degrades gracefully to a default model set — a request never fails because routing infrastructure hiccuped.

To see which task type your prompt was classified as, opt in to [router metadata](https://openrouter.ai/docs/guides/features/router-metadata) with the `X-OpenRouter-Metadata: enabled` header. The router stage in `openrouter_metadata.pipeline` then carries the tag at `data.task_type`, such as `code:debugging`. The field is absent when classification is unavailable.

## Usage

Set your model to `openrouter/auto`:

## Response

The response includes the `model` field showing which model was actually used:

## Session Stickiness

Unlike a fixed model slug, the Auto Router can pick a different model on every turn. To keep multi-turn conversations coherent, it remembers the model a conversation landed on and prefers it on later turns. OpenRouter recognizes the conversation from an explicit `session_id`, or from a fingerprint of your messages if you don’t send one. The router still ranks candidates from scratch on each turn, and it reuses the remembered model only while that model is still one of the top candidates for the new prompt. When the conversation shifts to a different kind of task, a better-suited model can win instead. The `model` field in each response tells you which one answered. Sessions also keep requests on the same provider, which works the same way as it does for any other model. See [Provider Sticky Routing](https://openrouter.ai/docs/guides/best-practices/prompt-caching#provider-sticky-routing) for how sessions are identified, how long they last, and how the `x-session-id` header works.

### Example with `session_id`

## Configuring Allowed Models

You can restrict which models the Auto Router can select from using request settings. This is useful when you want to limit routing to specific providers or model families.

### Via API Request

Use wildcard patterns to filter models. For example, `anthropic/*` matches all Anthropic models:

### Pattern Syntax

Pattern

Matches

`anthropic/*`

All Anthropic models

`openai/gpt-5*`

All GPT-5 variants

`google/*`

All Google models

`openai/gpt-5.1`

Exact match only

`*/claude-*`

Any provider with claude in model name

When no patterns are configured, the Auto Router considers every ranked candidate for your prompt’s task type.

## Excluding Models

Use `excluded_models` to prevent the Auto Router from selecting specific models for an individual request. It accepts the same wildcard pattern syntax as `allowed_models` described above. Exclusions are applied after `allowed_models`, so an excluded model is never selected even when it matches an allowed pattern.

Use exclusions for compliance restrictions, cost ceilings, or models that underperform for your task. If your restrictions leave no eligible models, the request fails with a `404` error: `No models match your request and model restrictions`.

## Cost Tier

Use the `cost_tier` request setting to choose the market’s cost band for routing. The tiers, from cheapest to most capable, are `low`, `medium`, `high`, `xhigh`, and `max`. `low` favors the cheapest capable models, while `max` favors the most capable models regardless of price. Requests that set no cost setting route as if you had asked for roughly the `low` band.

A tier is a band, not a ceiling, so models cheaper than the band are excluded as well as models above it. Within the tier you choose, models are still ranked by market spend share.

### Via API Request

### `cost_quality_tradeoff` Deprecated

`cost_quality_tradeoff` belonged to a previous version of the Auto Router and is deprecated, but remains accepted for backwards compatibility. If both parameters are provided, `cost_tier` takes precedence.

## Account Defaults

Instead of sending these settings on every request, you can save them for your account on your workspace’s [Routing page](https://openrouter.ai/settings/routing), where the Auto Router section stores allowed models and a cost preference. Saved values apply to every Auto Router request unless that request sets the same field, in which case the request wins — unless you enable the section’s “prevent overrides” toggle, which makes your saved values final. Saved values apply to both `openrouter/auto` and `openrouter/auto-beta`.

## Pricing

You pay the standard rate for whichever model is selected. There is no additional fee for using the Auto Router. To cap what a request may cost, [`provider.max_price`](https://openrouter.ai/docs/guides/routing/provider-selection#max-price) still applies: it filters the endpoints of whichever models the router resolves.

## Use Cases

-   **General-purpose applications**: When you don’t know what types of prompts users will send
-   **Cost optimization**: Let the router choose efficient models for simpler tasks
-   **Quality optimization**: Ensure complex prompts get routed to capable models
-   **Experimentation**: Discover which models work best for your use case

## Limitations

-   The router requires `messages` format (not `prompt`)
-   Streaming is supported
-   All standard OpenRouter features (tool calling, etc.) work with the selected model

-   [Body Builder](https://openrouter.ai/docs/guides/routing/routers/body-builder) - Generate multiple parallel API requests
-   [Latest Model Resolution](https://openrouter.ai/docs/guides/routing/routers/latest-resolution) - Always target the newest version of a model family
-   [Model Fallbacks](https://openrouter.ai/docs/guides/routing/model-fallbacks) - Configure fallback models
-   [Provider Selection](https://openrouter.ai/docs/guides/routing/provider-selection) - Control which providers are used
