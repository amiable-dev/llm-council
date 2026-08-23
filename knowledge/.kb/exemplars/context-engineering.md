---
title: "Context Engineering"
date: 2026-04-29
domain: llm
maturity: emerging
source_type: practitioner
topics: [context-engineering]
tags: [concept, ai-agents, llm, architecture, prompt-engineering, context, domain/llm, maturity/emerging, source-type/practitioner, topic/context-engineering]
status: draft
sources:
  - url: https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
    hash: sha256:afe8cb4270cce6ee7104903471226f908b70ad751336a80844ebe7b45832641a
    retrieved: 2026-08-21
    class: unclassified
    reachability: ok
  - url: https://x.com/karpathy/status/1937902205765607626
    hash: sha256:2f3a8e2639a2bb861836247163c5fd3d5108eceaee814bb7a1e92329bece1e52
    retrieved: 2026-08-21
    class: unclassified
    reachability: ok
---

# Context Engineering

## Definition
**Context engineering** is the practice of curating and maintaining the optimal set of tokens available to an LLM at inference time — including system instructions, tools, external data, message history, and MCP connections — to maximise the likelihood of a desired outcome. It supersedes prompt engineering by treating the *entire context state* as the engineering surface, not just the text of individual prompts.

## Explanation
Prompt engineering focuses on *what to write* in a system prompt — it was sufficient when most LLM use cases were one-shot classification or text generation tasks. Context engineering emerges as the natural progression when building multi-turn agents that operate over longer time horizons.

The shift is subtle but important: in a multi-turn agentic loop, a model generates new data every inference step — tool outputs, intermediate reasoning, observations — all of which could be relevant for the next step. The engineering challenge is deciding *what* from this constantly evolving universe of possible information to include in the next inference call.

Context engineering is therefore **iterative and continuous** rather than a discrete one-time task. It answers the question: *"Given what this agent is trying to do, what is the minimal, highest-signal set of tokens that should be in context right now?"*

### Key principles (from Anthropic)
- **System prompts at the right altitude:** Avoid brittle hardcoded if-else logic (too specific) and vague hand-wavy guidance (too general). Find the Goldilocks zone: specific enough to guide behaviour, flexible enough for model heuristics to operate.
- **Minimal viable tools:** Tool bloat is a top failure mode. Overlapping or ambiguous tools degrade performance. If a human can't decide which tool to use, neither can the model.
- **Tight, informative context:** Every component — prompts, tools, examples, message history — should carry high signal relative to its token cost.
- **Just-in-time retrieval over pre-loading:** Fetch data at runtime rather than stuffing everything upfront.
- **Compaction for long-horizon tasks:** Summarise and reinitialise context windows as they fill.

## Key Properties
- **Iterative** — context curation happens each inference step, not once at design time
- **Holistic** — encompasses system prompts, tools, examples, message history, retrieved data, and MCP connections simultaneously
- **Token-budget-aware** — treats context as a finite resource with diminishing marginal returns (see [[attention-budget]])
- **Signal-to-noise optimisation** — the goal is always the smallest set of highest-signal tokens for the task at hand

## Relationships
- Evolves from [[prompts-as-infrastructure]]: prompt engineering is a component of context engineering, not the whole picture
- Constrained by [[attention-budget]]: the n² attention mechanism makes every added token a real cost
- Degrades due to [[context-rot]]: longer contexts reduce recall accuracy across all models
- Implemented via [[just-in-time-context]]: runtime retrieval is a core context engineering strategy
- Extended by [[context-compaction]]: compaction handles the case where context windows fill up
- Extended by [[agentic-note-taking]]: persistent notes let agents maintain coherence across context resets
- Governs [[minimal-viable-tool-set]]: tool design is a context engineering concern, not just a UX one
- Related to [[multi-agent-systems]]: distributing context across specialised agents is an advanced context engineering strategy
- [[prompt-context-harness-loop-stack]] — occupies one rung of the prompt to context to harness to loop progression, not the whole of it

## Applications
- **Agent design:** When building any agent, treat context state as the primary design artefact — not just the system prompt
- **Debugging agent failures:** Most agent failures are context problems — too much noise, stale data, ambiguous tools, or lost state
- **Long-horizon tasks:** Use compaction and structured note-taking to maintain coherence across hours of work
- **Coding agents:** Hybrid approach — upfront project config (CLAUDE.md / AGENTS.md) + on-demand file retrieval (grep, glob)

## Study
- Flashcards: [[flashcards/context-engineering|Practice this concept]]

## Sources
- [Effective context engineering for AI agents — Anthropic Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — primary source; Anthropic's definitive guide
- [Context engineering vs. prompt engineering — Andrej Karpathy](https://x.com/karpathy/status/1937902205765607626) — the framing of context engineering as "art and science"

## See Also
- [[attention-budget]]
- [[context-rot]]
- [[just-in-time-context]]
- [[context-compaction]]
- [[agentic-note-taking]]
- [[minimal-viable-tool-set]]
- [[prompt-altitude]]
- [[progressive-disclosure-agents]]
- [[prompts-as-infrastructure]]
- [[multi-agent-systems]]
- [[context-compilation-pattern]]
- [[loop-engineering]]: context engineering is one of the primary levers for improving the [[agentic-coding-loop|agentic coding loop]] — better context means fewer iterations
- [[context-advantage]]: the human's context advantage over AI is what context engineering aims to systematically encode and transmit to agents
- [[llm-wiki-pattern]]: the wiki is a durable context layer; context engineering decides what to inject from it into the active prompt
- [[compilation-stage-knowledge-layer]]: complements context engineering — optimises what knowledge is available to retrieve before injection decisions are made
- [[metadata-as-code]]: provides a stable, versioned source of curated context for injection
- [[open-knowledge-format]]: OKF bundles are a primary source of the curated context that context engineering injects into agent prompts
- [[memory-as-harness]]: long-term memory stores are a key input to context engineering decisions
- [[agent-harness]]: harnesses that handle context injection automatically (Claude Code, OpenClaw) give context engineering benefits without per-application changes
