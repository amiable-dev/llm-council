---
title: Compositional Routing
date: 2026-08-23
domain: llm
maturity: established
source_type: research
tags: [concept, model-routing, domain/llm, maturity/established, source-type/research]
status: draft
sources:
  - url: https://arxiv.org/abs/2603.04445
---

# Compositional Routing

## Definition

Characterising routing systems along three dimensions — when decisions are made (pre-request, during, post-response), what information they use (query features, metadata, past performance), and how they compute (rules, classifiers, RL, cascades) — with production systems composing several paradigms rather than picking one.

## Explanation

The field's systematic survey finds no single routing paradigm wins: effective systems integrate multiple mechanisms under operational constraints, and well-designed routing can outperform the strongest individual model in the pool. The three-dimensional frame is the useful artifact: it locates any stack's mechanisms, exposes unoccupied positions, and explains why a rules-plus-classifier-plus-cascade architecture is the norm rather than a compromise.

## Key Properties

- Three axes: when x what x how, each independently chosen
- Production routing is compositional; single-paradigm systems are the exception
- Routing a good pool can beat the best single model in it

## Relationships

- [[portfolio-model-selection]] — extends the composition question from one model to a deliberating set
- [[cascade-structural-cost]] — prices one of the compositional paradigms

## Applications

Placing llm-council's L1-L4 stack on the map (it occupies all three when-positions) and auditing for unexploited axes.

## Sources

- https://arxiv.org/abs/2603.04445

## See Also

- [[portfolio-model-selection]]
