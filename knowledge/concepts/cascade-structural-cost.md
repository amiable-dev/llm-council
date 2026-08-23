---
title: Cascade Structural Cost
date: 2026-08-23
domain: llm
maturity: established
source_type: research
tags: [concept, model-routing, cost-optimisation, domain/llm, maturity/established, source-type/research]
status: draft
sources:
  - url: https://claude.ai/code/artifact/ccaabd90-28b1-442a-b7ba-bceda6aab4a0
  - url: https://arxiv.org/abs/2605.06350
---

# Cascade Structural Cost

## Definition

The floor a deferral cascade always pays: the shallow pass runs on every query, so escalation chains are bounded below by their first rung — and a lightweight pre-generation router often beats the whole cascade.

## Explanation

Cascade theory sharpened in 2026: multi-stage chains underperform optimised pairs, because every query funds the cheap attempt even when escalation was inevitable. The remedy is to predict the starting rung before generating, reserving cascades for genuinely uncertain cases. Designs that reuse the shallow pass inside the deeper one (prefix-superset model sets, as in llm-council's graduated depth) partially dodge the critique — escalation then only adds spend — but the prediction lesson stands.

## Key Properties

- The shallow pass is a tax on every query, escalated or not
- Pre-generation rung prediction beats always-climbing deferral
- Prefix-superset reuse converts escalation from rework into increment

## Relationships

- [[effort-routing]] — offers a cheaper first lever than adding cascade rungs

## Applications

Starting-rung prediction for llm-council's graduated depth (R4 in the 2026-08 routing review); deciding when a cascade is worth its floor at all.

## Sources

- https://claude.ai/code/artifact/ccaabd90-28b1-442a-b7ba-bceda6aab4a0
- https://arxiv.org/abs/2605.06350

## See Also

- [[effort-routing]]
