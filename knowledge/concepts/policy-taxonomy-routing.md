---
title: Policy Taxonomy Routing
date: 2026-08-23
domain: llm
maturity: emerging
source_type: research
tags: [concept, model-routing, domain/llm, maturity/emerging, source-type/research]
status: draft
sources:
  - url: https://arxiv.org/abs/2506.16655
---

# Policy Taxonomy Routing

## Definition

Routing queries by matching them to a human-authored domain-action taxonomy with a compact local model, with a decoupled route-to-model table — so preferences live in config and the model pool changes without retraining.

## Explanation

The pattern separates three things conventional routers fuse: what kinds of request exist (a natural-language taxonomy the operator owns), which route a query matches (a small self-hostable classifier), and which model serves each route (a plain table). Arch-Router demonstrates it with a 1.5B model beating proprietary routers on preference alignment; the shape fits sovereignty requirements because the weights are local and the policy is legible config rather than learned opacity.

## Key Properties

- Taxonomy in config: routing policy is reviewable text, not weights
- Route-to-model mapping changes without retraining anything
- A compact local matcher (~1.5B) suffices, keeping routing self-hosted

## Relationships

- [[portfolio-model-selection]] — supplies the query-understanding signal portfolio selection consumes
- [[compositional-routing]] — is one paradigm slot in a compositional routing stack

## Applications

The successor pattern to keyword-heuristic triage in llm-council (R2), with the heuristics retained as offline fallback.

## Sources

- https://arxiv.org/abs/2506.16655

## See Also

- [[portfolio-model-selection]]
