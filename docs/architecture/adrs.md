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

Each ADR follows the [Michael Nygard format](https://github.com/joelparkerhenderson/architecture-decision-record?tab=readme-ov-file#parameter-michael-nygard) as defined in the template `docs/adr/ADR-000-template.md`:

1.  **Title**: Short descriptive title.
2.  **Status**: The lifecycle state of the decision.
3.  **Context**: The problem and forces at play.
4.  **Decision**: The agreed-upon solution.
5.  **Consequences**: The trade-offs and outcomes (positive/negative).

### Status Lifecycle

The `Status` field tracks the lifecycle of a decision:

- **Draft**: Work in progress, not ready for review.
- **Proposed**: Ready for council review and discussion.
- **Accepted**: Approved and currently active. This is the **implementation status**.
- **Rejected**: Decision was considered but not taken.
- **Deprecated**: Decision was once active but is no longer valid (e.g., technology shift), without a direct replacement.
- **Superseded**: Decision has been explicitly replaced by a newer ADR. The header must link to the new ADR.

## Creating New ADRs

1.  Copy the template from `docs/adr/ADR-000-template.md`.
2.  Number sequentially (e.g., `ADR-040`).
3.  Open a Pull Request for discussion (Status: `Proposed`).
4.  Upon approval, merge and update Status to `Accepted`.

## Deprecating or Superseding

When a new decision replaces an old one:
1.  Create the new ADR (Status: `Accepted`).
2.  Update the old ADR's header:
    - Change Status to `Superseded`.
    - Add `Superseded By: [Link to new ADR]`.
    - (Optional) Add a note in the Context section explaining why it was replaced.

See the project GOVERNANCE.md for the detailed decision process.
