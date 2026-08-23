---
title: Deliberation Ground-Truth Index
date: 2026-08-23
domain: llm
maturity: emerging
source_type: practitioner
tags: [concept, model-routing, evaluation, domain/llm, maturity/emerging, source-type/practitioner]
status: draft
sources:
  - url: https://claude.ai/code/artifact/ccaabd90-28b1-442a-b7ba-bceda6aab4a0
    hash: sha256:0038079bd727e643eae55c497ad8bdf15e16587ecb0c7603797f796be0fbb4e8
    retrieved: 2026-08-23
    reachability: ok
  - url: https://arxiv.org/abs/2606.06924
---

# Deliberation Ground-Truth Index

## Definition

Per-session, task-local model-quality measurements generated as exhaust by structured peer review — the scarce supervision signal that every learned router lacks, produced continuously wherever deliberation already runs.

## Explanation

Routers are starved for per-request quality labels: market spend is a popularity proxy, arena preferences are generic, curated evals are expensive and stale. A deliberating council produces the missing signal for free — every session yields peer-reviewed rankings of real answers to real questions. That reframes the performance index from a routing input into the differentiated asset of the routing economy, with one honest caveat: the flywheel is tenant-local, so its confidence grows with a tenant's own traffic and cannot be centralised by an OSS project without becoming a different kind of product.

## Key Properties

- Quality labels as a by-product of deliberation, not a labelling programme
- Task-local and fresh where arena and eval signals are generic and stale
- Tenant-local flywheel: confidence gates on per-tenant session volume

## Relationships

- [[portfolio-model-selection]] — is the scoring signal portfolio selection blends by confidence tier

## Applications

llm-council's performance-blended selection (ADR-044 P1); the §7 strategic verdict to keep routing embedded and treat the index as the asset.

## Sources

- https://claude.ai/code/artifact/ccaabd90-28b1-442a-b7ba-bceda6aab4a0
- https://arxiv.org/abs/2606.06924

## See Also

- [[portfolio-model-selection]]
