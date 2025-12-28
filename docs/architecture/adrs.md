# Architecture Decision Records

This project uses Architecture Decision Records (ADRs) to document significant technical decisions.

## Active ADRs

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-015](../adr/ADR-015-bias-auditing.md) | Per-Session Bias Audit | Implemented |
| [ADR-016](../adr/ADR-016-structured-rubric-scoring.md) | Structured Rubric Scoring | Implemented |
| [ADR-018](../adr/ADR-018-cross-session-bias-aggregation.md) | Cross-Session Bias Aggregation | Implemented |
| [ADR-020](../adr/ADR-020-not-diamond-integration-strategy.md) | Query Triage Layer | Implemented |
| [ADR-022](../adr/ADR-022-tiered-model-selection.md) | Tiered Model Selection | Implemented |
| [ADR-023](../adr/ADR-023-multi-router-gateway-support.md) | Gateway Layer | Implemented |
| [ADR-024](../adr/ADR-024-unified-routing-architecture.md) | Unified Routing Architecture | Implemented |
| [ADR-025](../adr/ADR-025-future-integration-capabilities.md) | Future Integration | Implemented |
| [ADR-026](../adr/ADR-026-dynamic-model-intelligence.md) | Model Intelligence Layer | Implemented |
| [ADR-027](../adr/ADR-027-frontier-tier.md) | Frontier Tier | Implemented |
| [ADR-028](../adr/ADR-028-dynamic-candidate-discovery.md) | Dynamic Candidate Discovery | Implemented |
| [ADR-029](../adr/ADR-029-model-audition-mechanism.md) | Model Audition Mechanism | Implemented |
| [ADR-030](../adr/ADR-030-scoring-refinements.md) | Enhanced Circuit Breaker | Implemented |
| [ADR-031](../adr/ADR-031-configuration-modernization.md) | Evaluation Configuration | Implemented |

## ADR Format

Each ADR follows this structure:

1. **Title** - Short descriptive title
2. **Status** - Draft, Proposed, Accepted, Implemented, Deprecated
3. **Context** - What problem are we solving?
4. **Decision** - What did we decide?
5. **Consequences** - What are the trade-offs?

## Creating New ADRs

1. Copy the template from `docs/adr/ADR-000-template.md`
2. Number sequentially (ADR-034, ADR-035, etc.)
3. Open PR for discussion
4. Update status as implementation progresses

See the project GOVERNANCE.md for the decision process.
