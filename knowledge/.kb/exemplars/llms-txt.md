---
title: "llms.txt"
date: 2026-07-27
domain: standards
maturity: emerging
source_type: practitioner
topics: [protocols]
tags: [concept, ai-agents, standards, discovery, llm, seo, domain/standards, maturity/emerging, source-type/practitioner, topic/protocols]
status: draft
sources:
  - url: https://baselinelabs.ai/blog/llms-txt-google-search
    hash: sha256:2f9fb4985afa7b55761a9842a1739349ef465cc2847ff7b5d813f702e546064e
    retrieved: 2026-08-21
    class: unclassified
    reachability: ok
  - url: https://www.greadme.com/blog/seo/is-llms-txt-worth-it-for-ai-search
    hash: sha256:7658323075eafc82f41d6b445201bdd4e823f549773b4928c5d0845b96db7297
    retrieved: 2026-08-21
    class: unclassified
    reachability: ok
  - url: https://medium.com/@kaispriestersbach/the-llms-txt-is-dead-more-precisely-a-dud-ab7bee4f469c
    hash: sha256:6852c2f68af01b2d446678a5deaec643b2cc7dc18ad65235c99540b17f0e7103
    retrieved: 2026-08-21
    class: unclassified
    reachability: ok
  - url: https://limy.ai/blog/llms.txt-in-2026-the-full-guide
    hash: sha256:955bbb7872560e52edc864c959b69f0b67527ebe48e4855ae185763a95744b46
    retrieved: 2026-08-21
    class: unclassified
    reachability: ok
---

# llms.txt

## Definition
A community-proposed convention (Jeremy Howard, Answer.AI, 2024) for a plain Markdown file served at a site's root (`/llms.txt`, with an optional `/llms-full.txt` variant carrying the full content) that lists the pages an AI agent should read first to understand a site. It has no formal standards-body backing and no provider has committed to consuming it as a ranking or citation signal — its real, measured use is as a navigation index for coding agents and agentic browsers reading developer documentation, not as an SEO/GEO lever for general web visibility.

## Explanation
llms.txt was marketed as "robots.txt for AI" — publish it and language models will read your site and cite you. That framing has been directly falsified. Google's Search Central AI-optimisation guide, updated June 15 2026, states plainly that Search does not use machine-readable files like llms.txt for rankings or AI Overviews "as Google Search itself doesn't use them." Gary Illyes confirmed in July 2025 that Google has no plans to support it; John Mueller compared it on Reddit to the discredited keywords meta tag — a file where the site owner tells you what the site is about, which is exactly the kind of unverified claim search engines learned to distrust decades ago.

The adoption data backs the null result up from multiple angles:
- SE Ranking's analysis of ~300,000 domains found ~10% adoption, but a statistical model and an XGBoost classifier both found **zero correlation** with AI citations — removing the llms.txt variable as a feature actually *improved* the model's accuracy.
- Ahrefs tracked 137,210 domains and found 97% of llms.txt files were never fetched at all in May 2026; of the 3% that were fetched, only 19.5% of those requests came from named AI tools (GPTBot first, Claude Code second).
- Limy.AI's 90-day server-log study saw roughly 408 targeted llms.txt fetches out of more than 500 million AI bot events. Otterly.AI found just 84 of 62,100 AI bot visits (0.1%) hit the file.

Yet Stripe, Vercel, Cloudflare, OpenAI, Anthropic and Mastercard all ship one — not for search visibility, but because a specific and growing class of tools (Cursor, Windsurf, Claude Code, GitHub Copilot, Cline, Aider) reads `/llms.txt` by convention as a navigation hint when a developer asks the agent to "use the Stripe docs." For that audience it functions like a sitemap does for Googlebot: a structured index of where the useful content lives, sparing the agent a crawl-and-guess. Chrome's Lighthouse 13.3 (May 2026) moved llms.txt auditing into the default "Agentic Browsing" category even as Google Search says to ignore it — a real split inside Google between teams optimising for different consumers of the same file.

This session's own research corroborates the developer-docs use case directly: both `agentskills.io` and `code.claude.com` serve `llms.txt`, and pages on those sites carried headers instructing agents to fetch the index first.

## Key Properties
- **No formal governance** — a community convention, not a standard from IETF, W3C, or any foundation (contrast with [[agent-to-agent-protocol]], which moved to Linux Foundation governance)
- **Zero measured search/citation effect** — confirmed by Google directly and by four independent third-party studies (SE Ranking, Ahrefs, Limy.AI, Otterly.AI)
- **Real but narrow adoption** — ~10% of general domains, but near-universal among sites whose primary audience is developers using coding agents
- **Low cost, asymmetric bet** — roughly half a day to draft, no ongoing maintenance, no penalty risk; worth shipping for agent navigation even though it does nothing for search
- **Split verdict within Google itself** — Search Central says skip it; Chrome Lighthouse audits it under "Agentic Browsing"

## Relationships
- Contrasts with [[agent-to-agent-protocol]]: A2A is formally governed (Linux Foundation, v1.0, signed identity) and solves agent↔agent delegation; llms.txt is an ungoverned convention solving a narrower agent↔documentation navigation problem. The comparison is the core lesson of this research — standards that stick solve a problem for *developers building agents*, not for *marketers courting agents*.
- Related to [[agentic-resource-discovery]] and [[capability-registry]]: all three are discovery-layer mechanisms, but llms.txt indexes *content* for an agent to read, while ARD/capability registries index *capabilities* an agent can invoke.
- Related to robots.txt / AI crawler controls: the inverse mechanism — robots.txt is about *denying* crawler access and is well-enforced; llms.txt is about *inviting* it and is barely read.

## Applications
- **Developer documentation sites** (API docs, SDK references, CLI tool docs): publish `/llms.txt` so coding agents like Claude Code or Cursor can navigate the docs when a developer says "check the X API docs" — genuinely useful, low effort.
- **Do not** publish it expecting any effect on Google Search, AI Overviews, or general AI-search citation — the data is unambiguous that it does nothing there.
- **Homelab/OpenClaw relevance:** if any part of the PKM vault or an internal API (reminder-gw, knowledge-gw, update-gw) is ever exposed for agent consumption, an `llms.txt` is worth adding purely for agent navigation, with honest expectations set from the start.

## Sources
- [llms.txt does nothing for Google Search — so what's it for?](https://baselinelabs.ai/blog/llms-txt-google-search) — primary source; Google's June 2026 Search Central position, the SE Ranking/Ahrefs/Limy.AI/Otterly.AI adoption data, Mueller's keywords-meta-tag comparison
- [Is llms.txt worth it for AI search?](https://www.greadme.com/blog/seo/is-llms-txt-worth-it-for-ai-search) — corroborates "Google confirmed it directly"; notes disputed OpenAI crawling claims
- [The llms.txt is dead, more precisely a dud](https://medium.com/@kaispriestersbach/the-llms-txt-is-dead-more-precisely-a-dud-ab7bee4f469c) — the sceptical case; confirms Anthropic/OpenAI/Perplexity use it on dev docs specifically
- [llms.txt in 2026: the full guide](https://limy.ai/blog/llms.txt-in-2026-the-full-guide) — Gary Illyes' keywords-meta-tag comparison, 90-day server-log study

## See Also
- [[agent-to-agent-protocol]]
- [[agentic-resource-discovery]]
- [[capability-registry]]
- [[ai-capability-catalog]]
- [[agent-skills-open-standard]] — agentskills.io serves its own documentation index via `llms.txt`, a live production example of this convention
