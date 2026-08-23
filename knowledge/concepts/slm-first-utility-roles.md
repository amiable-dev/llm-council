---
title: SLM-First Utility Roles
date: 2026-08-23
domain: llm
maturity: emerging
source_type: practitioner
tags: [concept, model-routing, domain/llm, maturity/emerging, source-type/practitioner]
status: draft
sources:
  - url: https://arize.com/blog/nvidias-small-language-models-are-the-future-of-agentic-ai-paper/
    hash: sha256:0f0914fbd94b49c8714064ca1607ce0edf9a655816cdfb1425b4ec009dbba7e6
    retrieved: 2026-08-23
    reachability: ok
---

# SLM-First Utility Roles

## Definition

Assigning small language models to the narrow, repetitive, mechanical subtasks of an agentic pipeline — classification, normalisation, parsing, screening — and reserving frontier models for the judgment that actually needs them.

## Explanation

The SLM-first thesis holds that most agentic substeps are narrow and repetitive, where small models carry a 10-30x cost advantage and adequate reliability, with escalation for the genuinely hard turns. For a deliberation pipeline the mapping is direct: triage, style normalisation, ranking-parse fallbacks and screening need no frontier model, and moving them to local or quick-tier SLMs concentrates spend where deliberation quality lives — while strengthening any offline story, since the utility roles stop needing external APIs.

## Key Properties

- 10-30x cost advantage on narrow repetitive subtasks
- Escalate the hard turns; do not staff every step with a frontier model
- Local SLM utility roles double as the offline fallback path

## Relationships

- [[effort-routing]] — complements it: right-size effort on big models, right-size the model on small tasks
- [[policy-taxonomy-routing]] — is itself an SLM utility role — a compact local matcher

## Applications

Moving llm-council's mechanical substeps (triage, normalisation, parsing, screening) to quick-tier or local models (R9).

## Sources

- https://arize.com/blog/nvidias-small-language-models-are-the-future-of-agentic-ai-paper/

## See Also

- [[effort-routing]]
