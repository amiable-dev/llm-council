---
title: Portfolio Model Selection
date: 2026-08-23
domain: llm
maturity: emerging
source_type: research
tags: [concept, model-routing, multi-agent, domain/llm, maturity/emerging, source-type/research]
status: draft
sources:
  - url: https://claude.ai/code/artifact/ccaabd90-28b1-442a-b7ba-bceda6aab4a0
    hash: sha256:0038079bd727e643eae55c497ad8bdf15e16587ecb0c7603797f796be0fbb4e8
    retrieved: 2026-08-23
    reachability: ok
  - url: https://arxiv.org/abs/2503.10657
    hash: sha256:85b1e7d6bd9218dd93676c44a890ef517d57337f21176480372e501f9bf9c37b
    retrieved: 2026-08-23
    reachability: ok
---

# Portfolio Model Selection

## Definition

Choosing a SET of models to deliberate together — under diversity, anti-herding, and lifecycle constraints — rather than routing a query to the single best model, which is the only problem commercial routers solve.

## Explanation

Every routing product and platform feature (Bedrock, Azure, OpenRouter auto) selects one model per query. A deliberating council needs the complement: a portfolio whose members are individually capable and collectively diverse, with graduated membership (shadow audition before voting authority) and penalties against herding toward whatever is currently popular. As of 2026-08 this capability exists in research papers and in llm-council's selection layer, but no product serves it — which makes it a differentiated build, not a commodity to consume.

## Key Properties

- Selects a set, not a winner: diversity and anti-herding are first-class constraints
- Membership has a lifecycle: shadow audition, graduation, circuit-breaking
- Unserved by the 2026 routing market — every product routes to one model

## Relationships

- [[deliberation-ground-truth-index]] — supplies the quality signal portfolio scoring blends in
- [[cascade-structural-cost]] — bounds how cheaply a portfolio can be engaged incrementally
- [[slm-first-utility-roles]] — delegates its mechanical substeps to SLM utility roles

## Applications

llm-council's candidate selection (ADR-026/028/029); the routing-kernel internal decoupling decided in the 2026-08 routing strategy review.

## Sources

- https://claude.ai/code/artifact/ccaabd90-28b1-442a-b7ba-bceda6aab4a0
- https://arxiv.org/abs/2503.10657

## See Also

- [[deliberation-ground-truth-index]]
