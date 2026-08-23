---
title: Effort Routing
date: 2026-08-23
domain: llm
maturity: emerging
source_type: research
tags: [concept, model-routing, cost-optimisation, domain/llm, maturity/emerging, source-type/research]
status: draft
sources:
  - url: https://claude.ai/code/artifact/ccaabd90-28b1-442a-b7ba-bceda6aab4a0
    hash: sha256:0038079bd727e643eae55c497ad8bdf15e16587ecb0c7603797f796be0fbb4e8
    retrieved: 2026-08-23
    reachability: ok
  - url: https://arxiv.org/abs/2606.23181
    hash: sha256:9f4d4000b9e1831635f8e3a063b0920588350c33abd71a2721c3f089043b4dd7
    retrieved: 2026-08-23
    reachability: ok
---

# Effort Routing

## Definition

Treating reasoning effort as a routed, per-query dimension — (model, effort) chosen together — instead of fixing thinking budgets per tier, exploiting the cheapest compute lever available because nothing else changes.

## Explanation

Frontier systems route internally between fast and thinking variants and expose effort parameters programmatically; adaptive thinking-budget research shows per-query allocation consistently beating uniform budgets. For a consumer, varying effort on the SAME model is cheaper than switching models: the cache stays warm, the bill shrinks, and the routing signal required (complexity, consensus state) is already computed. Effort routing therefore sits before model switching in the optimisation order.

## Key Properties

- A second routing dimension on the same model — no cache forfeiture
- Per-query allocation beats uniform tier budgets by consistent margins
- Uses complexity and consensus signals the pipeline already produces

## Relationships

- [[cascade-structural-cost]] — substitutes for escalation rungs when the container model already suffices

## Applications

R6 in the 2026-08 routing review: making reasoning_effort per-query in llm-council rather than a tier constant.

## Sources

- https://claude.ai/code/artifact/ccaabd90-28b1-442a-b7ba-bceda6aab4a0
- https://arxiv.org/abs/2606.23181

## See Also

- [[cascade-structural-cost]]
