---
title: Cost-Quality Frontier Evaluation
date: 2026-08-23
domain: llm
maturity: established
source_type: research
tags: [concept, model-routing, domain/llm, maturity/established, source-type/research]
status: draft
sources:
  - url: https://arxiv.org/abs/2403.12031
    hash: sha256:6ae010d0c7a59e8deb5cb4dd36be7e55ced0bbef4cb8f730c65d76e3fae5d685
    retrieved: 2026-08-23
    reachability: ok
---

# Cost-Quality Frontier Evaluation

## Definition

Evaluating routing systems on the full cost-quality frontier curve they trace — not at a single operating point — so different routers, cascades, and depth policies compare on the same axes at every budget.

## Explanation

Point metrics hide the trade-off that routing exists to manage: a router that wins at one budget can lose everywhere else. RouterBench formalises frontier-curve evaluation over hundreds of thousands of inference outcomes and provides the theoretical frame; the practical consequence for any deliberation system is that bench reporting should emit frontier curves (quality vs spend across configurations), making activation decisions measurable instead of argued.

## Key Properties

- The unit of comparison is a curve, not a number
- Frontier position is budget-relative: report the whole trade-off
- One reporting change upgrades an existing bench matrix to frontier form

## Relationships

- [[deliberation-ground-truth-index]] — supplies the quality axis the frontier plots
- [[calibrated-consensus-stopping]] — is one of the policies the frontier makes comparable

## Applications

RouterBench-style frontier reporting in llm-council's bench matrix (R7) — the measurement gate for R1/R3/R5 activation decisions.

## Sources

- https://arxiv.org/abs/2403.12031

## See Also

- [[deliberation-ground-truth-index]]
