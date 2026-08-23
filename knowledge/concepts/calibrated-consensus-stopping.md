---
title: Calibrated Consensus Stopping
date: 2026-08-23
domain: llm
maturity: emerging
source_type: research
tags: [concept, model-routing, domain/llm, maturity/emerging, source-type/research]
status: draft
sources:
  - url: https://arxiv.org/abs/2605.04236
---

# Calibrated Consensus Stopping

## Definition

Stopping ensemble deliberation on calibrated commit signals — committing early on genuine consensus and falling back on fragmented evidence — rather than running a fixed number of rounds or requiring strict unassailability.

## Explanation

Adaptive stopping, not richer inter-agent communication, is what drives ensemble efficiency: DASE shows sparse injection with a good stopping rule matches dense injection, and that commit-type partitions carry large routing-quality gaps (25-40pp between commit classes). A strict unassailable-margin rule is the provably-safe end of this spectrum; a calibrated mode stops earlier at bounded risk, and shadow logs can quantify the conservatism gap before switching.

## Key Properties

- Commit signals are calibrated against outcomes, not fixed thresholds
- The commit-type partition itself is routing signal (which class a query lands in)
- Stopping quality dominates injection bandwidth as the efficiency lever

## Relationships

- [[cascade-structural-cost]] — bounds deliberation depth the way rung prediction bounds cascade depth

## Applications

A DASE-style opt-in stopping rule beside llm-council's strict Borda-unassailability mode (R5), quantified from existing shadow telemetry.

## Sources

- https://arxiv.org/abs/2605.04236

## See Also

- [[cascade-structural-cost]]
