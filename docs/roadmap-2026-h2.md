# Roadmap — 2026 H2

Five highest-value deliverables, identified 2026-07-02 by (a) a reverse-order ADR
sweep for unimplemented items and (b) a survey of the July-2026 GenAI landscape.
Ordered by value; #1 is in flight (ADR-044).

## 1. Compute-Optimal Deliberation — ADR-044 (in flight)

**What:** Wire the internal performance index (ADR-026 P3, currently write-only)
and the cost-per-quality scores (ADR-011 P3, currently unconsumed) into model
selection; add early-consensus termination (ADR-040 Option F) and graduated
deliberation depth. Subsumes drafts ADR-039 (LLMRouter) and ADR-043 (Pareto).

**Why now:** RouteLLM-class routers demonstrate ~85% cost reduction at ~95%
quality; compute-optimal test-time scaling (spend depth only where the query
needs it) beats fixed-depth ensembles; heterogeneous-model ensembles are cited
as underexplored — this project is one. The telemetry needed was shipped in
v0.25.x–v0.27.x and has no consumer yet.

## 2. MCP 2026-07-28 Adoption — Tasks primitive + Server Card

**What:** Adopt the MCP 2026-07-28 spec (final 2026-07-28): the **Tasks
primitive** for long-running deliberations (submit → poll/resume; survives
client disconnects) and a **Server Card** (`.well-known` metadata) for
registry discovery; stateless transport for load-balanced serving.

**Why now:** The council's #1 documented UX pain is MCP client timeouts on
high/reasoning tiers (README instructs raising `MCP_TIMEOUT`); Tasks is
purpose-built for it. Server Cards make the council discoverable across
19k+-server MCP registries. Extends ADR-012.

## 3. Streaming Deliberation, end-to-end

**What:** Stream Stage-1 responses as they land, ranking events as they
resolve, and chairman synthesis token-by-token — over the existing SSE
endpoint and MCP progress/Tasks. Builds on the true gateway SSE shipped in
v0.27.1.

**Why now:** No implementation in the growing llm-council ecosystem streams;
a 30–600s deliberation behind a spinner is the product's felt weakness.
Listed as the first "future enhancement" in CLAUDE.md.

## 4. Verifier Calibration & Judge Reliability

**What:** Calibrate `verify`'s confidence signal against observed outcomes
(the `.council/logs` transcript corpus is training data we own); add a
lightweight screening judge before full-council verification; harden
UNCLEAR/timeout semantics; position-debias per bias-amplification research.
ADR-036 Phase 2 (calibration report) + ADR-015/017.

**Why now:** 2026 judge research shows multi-agent judges can *amplify* bias
and confidence signals are systematically miscalibrated — matching our own
operational evidence (multi-round verify asymptotes with zero blocking
issues; confidence pinned below its own PASS threshold). Verification is the
flagship CI-gate feature; its reliability is the product.

## 5. Council Quality Benchmark + Golden-Dataset Regression

**What:** A published benchmark answering "when does a council beat a single
frontier model, per dollar?" (uses ADR-011 cost ground truth), plus a
golden-dataset regression suite in CI so council quality can't silently
drift. ADR-036 Phases 2–3 slice; DeepEval/RAGAS bridges.

**Why now:** Positions the project with evidence in an increasingly crowded
llm-council space, and produces the empirical tuning data #1's router needs.

---

### Sources (July 2026)

- [Multi-Agent Verification: Scaling Test-Time Compute](https://arxiv.org/pdf/2502.20379) · [Compute-Optimal Scaling as an Optimizable Graph](https://arxiv.org/pdf/2511.00086) · [Mixture-of-Models: N-Way Self-Evaluating Deliberation](https://arxiv.org/pdf/2601.16863)
- [The 2026 MCP Roadmap](https://blog.modelcontextprotocol.io/posts/2026-mcp-roadmap/) · [MCP 2026-07-28 Release Candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
- [LLM Model Routing in 2026](https://www.digitalapplied.com/blog/llm-model-routing-2026-cost-quality-optimization-engineering-guide) · [Routing, Cascades, and User Choice](https://arxiv.org/pdf/2602.09902) · [Model Routing as a Trust Problem](https://arxiv.org/pdf/2605.01710)
- [Agent-as-a-Judge Survey](https://arxiv.org/pdf/2601.05111) · [Judging with Many Minds (bias amplification)](https://arxiv.org/pdf/2505.19477) · [LLM-as-a-Judge in 2026 — DeepEval](https://deepeval.com/guides/guides-llm-as-a-judge)
- [Awesome LLM Council Projects](https://github.com/danielrosehill/Awesome-LLM-Council-Projects)
