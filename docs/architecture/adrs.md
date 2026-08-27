# Architecture Decision Records

This project uses Architecture Decision Records (ADRs) to document significant technical decisions.

## All ADRs

Every ADR in the repository, newest last. **Status** distinguishes live decisions from superseded ones — a superseded ADR is kept rather than deleted so the reasoning behind a reversal stays readable.

Four numbers appear twice (ADR-042, 051, 052, 053): those decisions have a companion *Implementation Spec* alongside the ADR itself — the ADR holds the decision, the spec holds the delivery detail.

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](../adr/ADR-001-Council-Summary.md) | AI-Integrated Incident Response System | Draft |
| [ADR-007](../adr/ADR-007-scoring-methodology.md) | Council Scoring Methodology | Proposed |
| [ADR-008](../adr/ADR-008-package-structure.md) | Package Structure - Library with Optional MCP | Accepted |
| [ADR-009](../adr/ADR-009-http-api-open-core-boundary.md) | HTTP API and Open Core Boundary | Accepted |
| [ADR-010](../adr/ADR-010-consensus-mechanisms.md) | Consensus Mechanism - Normalized Score Averaging | Proposed |
| [ADR-011](../adr/ADR-011-cost-tracking.md) | Cost and Token Accounting | Implemented |
| [ADR-012](../adr/ADR-012-mcp-server-reliability.md) | MCP Server Reliability and Long-Running Operation Handling | Implemented |
| [ADR-013](../adr/ADR-013-secure-api-key-handling.md) | Secure API Key Handling | Implemented |
| [ADR-014](../adr/ADR-014-verbosity-penalty-prompts.md) | Verbosity Penalty in Evaluation Prompts | Superseded |
| [ADR-015](../adr/ADR-015-bias-auditing.md) | Bias Auditing and Length Correlation Tracking | Implemented |
| [ADR-016](../adr/ADR-016-structured-rubric-scoring.md) | Structured Rubric Scoring | Implemented |
| [ADR-017](../adr/ADR-017-response-order-randomization.md) | Response Order Randomization | Implemented |
| [ADR-018](../adr/ADR-018-cross-session-bias-aggregation.md) | Cross-Session Bias Aggregation | Accepted |
| [ADR-019](../adr/ADR-019-outlook-email-itil-analysis.md) | AI-Powered Outlook Email Analysis for ITIL Operations Insights | Proposed |
| [ADR-020](../adr/ADR-020-not-diamond-integration-strategy.md) | Not Diamond Integration Strategy for LLM Council Ecosystem | Implemented |
| [ADR-021](../adr/ADR-021-quint-code-fpf-integration.md) | Quint Code and First Principles Framework (FPF) Integration | Proposed |
| [ADR-022](../adr/ADR-022-tiered-model-selection.md) | Tiered Model Selection for Confidence Levels | Implemented |
| [ADR-023](../adr/ADR-023-multi-router-gateway-support.md) | Multi-Router Gateway Support (OpenRouter, Requesty, Direct APIs) | Implemented |
| [ADR-024](../adr/ADR-024-unified-routing-architecture.md) | Unified Routing Architecture | Proposed |
| [ADR-025](../adr/ADR-025-future-integration-capabilities.md) | Future Integration Capabilities | Accepted |
| [ADR-026](../adr/ADR-026-dynamic-model-intelligence.md) | Dynamic Model Intelligence and Benchmark-Driven Selection | Implemented |
| [ADR-027](../adr/ADR-027-frontier-tier.md) | Frontier Tier | Accepted |
| [ADR-028](../adr/ADR-028-dynamic-candidate-discovery.md) | Dynamic Candidate Discovery | Accepted |
| [ADR-029](../adr/ADR-029-model-audition-mechanism.md) | Model Audition Mechanism | Accepted |
| [ADR-030](../adr/ADR-030-scoring-refinements.md) | Scoring Refinements | Accepted |
| [ADR-031](../adr/ADR-031-configuration-modernization.md) | Configuration Modernization & Cleanup | Accepted |
| [ADR-032](../adr/ADR-032-complete-config-migration.md) | Complete Configuration Migration & config.py Deletion | Accepted |
| [ADR-033](../adr/ADR-033-oss-community-infrastructure.md) | Open Source Community Infrastructure | Draft |
| [ADR-034](../adr/ADR-034-agent-skills-verification.md) | Agent Skills Integration for Work Verification | Draft |
| [ADR-035](../adr/ADR-035-devsecops-implementation.md) | DevSecOps Implementation for Open Source | Accepted |
| [ADR-036](../adr/ADR-036-output-quality-quantification.md) | Output Quality Quantification Framework | — |
| [ADR-037](../adr/ADR-037-n8n-workflow-integration.md) | n8n Workflow Automation Integration | Draft |
| [ADR-038](../adr/ADR-038-one-click-deployment-strategy.md) | One-Click Deployment Strategy | — |
| [ADR-039](../adr/ADR-039-llmrouter-integration.md) | One-Click Deployment Strategy | Superseded |
| [ADR-040](../adr/ADR-040-verification-timeout-observability.md) | Verification Timeout Guardrails and Observability | Accepted |
| [ADR-041](../adr/ADR-041-verification-telemetry-wiring.md) | Verification Telemetry Wiring | Accepted |
| [ADR-042](../adr/ADR-042-implementation-spec.md) | Implementation Spec — Verify Evidence Injection | Implementation Spec |
| [ADR-042](../adr/ADR-042-verify-evidence-injection.md) | Verify Evidence Injection — Pre-computed Analysis as Council Context | Draft |
| [ADR-043](../adr/ADR-043-pareto-router-integration.md) | OpenRouter Pareto Router Integration | Superseded |
| [ADR-044](../adr/ADR-044-compute-optimal-deliberation.md) | Compute-Optimal Deliberation | Implemented |
| [ADR-045](../adr/ADR-045-mcp-2026-adoption.md) | MCP 2026-07-28 Specification Adoption (Tasks, Server Card, Stateless Transport) | Implemented |
| [ADR-046](../adr/ADR-046-streaming-deliberation.md) | Streaming Deliberation | Implemented |
| [ADR-047](../adr/ADR-047-verifier-calibration.md) | Verifier Calibration & Judge Reliability | Implemented |
| [ADR-048](../adr/ADR-048-quality-benchmark.md) | Council Quality Benchmark & Golden-Dataset Regression | Implemented |
| [ADR-049](../adr/ADR-049-prompt-caching-across-gateways.md) | Prompt Caching Across Gateways | Implemented |
| [ADR-050](../adr/ADR-050-posthog-llm-analytics-emission.md) | PostHog LLM Analytics Emission | Implemented |
| [ADR-051](../adr/ADR-051-implementation-spec.md) | Implementation Spec — Verify Findings Channel | Draft |
| [ADR-051](../adr/ADR-051-verify-findings-channel.md) | Verify Findings Channel & Verdict–Evidence Consistency | Implemented |
| [ADR-052](../adr/ADR-052-implementation-spec.md) | Implementation Spec — Structured-Findings Rollout & Enablement | Implementation Spec |
| [ADR-052](../adr/ADR-052-structured-findings-rollout.md) | Structured-Findings Rollout & Enablement | Proposed |
| [ADR-053](../adr/ADR-053-implementation-spec.md) | Implementation Spec — Delivery Plan, Disclosure, and Child Breakdown | Proposed |
| [ADR-053](../adr/ADR-053-verify-file-selection-trust-boundary.md) | Verify File Selection — Decodability, Reviewability, and the Trust Boundary | Implemented |
| [ADR-054](../adr/ADR-054-verify-confidence-semantics.md) | What `confidence` Means in verify() — and How to Calibrate It | Accepted |
| [ADR-055](../adr/ADR-055-chairman-resilience.md) | Chairman Resilience — Dynamic Fallback for Stage-3 Synthesis | Proposed |

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
