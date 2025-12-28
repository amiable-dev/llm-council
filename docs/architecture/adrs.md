# Architecture Decision Records

This project uses Architecture Decision Records (ADRs) to document significant technical decisions.

## Active ADRs

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-015](../../docs/adr/ADR-015-per-session-bias-audit.md) | Per-Session Bias Audit | Implemented |
| [ADR-016](../../docs/adr/ADR-016-structured-rubric-scoring.md) | Structured Rubric Scoring | Implemented |
| [ADR-018](../../docs/adr/ADR-018-cross-session-bias-aggregation.md) | Cross-Session Bias Aggregation | Implemented |
| [ADR-020](../../docs/adr/ADR-020-not-diamond-integration.md) | Query Triage Layer | Implemented |
| [ADR-022](../../docs/adr/ADR-022-tiered-model-selection.md) | Tiered Model Selection | Implemented |
| [ADR-023](../../docs/adr/ADR-023-gateway-layer.md) | Gateway Layer | Implemented |
| [ADR-024](../../docs/adr/ADR-024-unified-routing-architecture.md) | Unified Routing Architecture | Implemented |
| [ADR-025](../../docs/adr/ADR-025-future-integration.md) | Future Integration | Implemented |
| [ADR-025b](../../docs/adr/ADR-025b-jury-mode.md) | Jury Mode | Implemented |
| [ADR-026](../../docs/adr/ADR-026-model-intelligence-layer.md) | Model Intelligence Layer | Implemented |
| [ADR-027](../../docs/adr/ADR-027-frontier-tier.md) | Frontier Tier | Implemented |
| [ADR-028](../../docs/adr/ADR-028-dynamic-discovery.md) | Dynamic Candidate Discovery | Implemented |
| [ADR-029](../../docs/adr/ADR-029-model-audition.md) | Model Audition Mechanism | Implemented |
| [ADR-030](../../docs/adr/ADR-030-circuit-breaker.md) | Enhanced Circuit Breaker | Implemented |
| [ADR-031](../../docs/adr/ADR-031-evaluation-config.md) | Evaluation Configuration | Implemented |
| [ADR-033](../../docs/adr/ADR-033-oss-community-infrastructure.md) | OSS Community Infrastructure | In Progress |

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

See [GOVERNANCE.md](../../GOVERNANCE.md) for the decision process.
