# Model Routing Strategy 2026

**Type:** Whitepaper / strategy review
**Date:** 2026-08-22
**Author:** Chris Joseph, with Claude (deep-research assisted)
**Scope:** L1–L4 routing & model-selection stack (ADR-020/022/024/026/028/029/044) vs. the August 2026 industry state; strategic assessment of decoupling routing as a separate product
**Feeds:** prospective ADR-055 (contextual routing), ADR-020 amendment, ADR-048 bench reporting

---

## 1. Executive summary

### The problem / opportunity

LLM Council's economics are dominated by one variable: **how much frontier-model inference each question buys**. A full council multiplies every query by N members plus N reviewers plus a chairman — the deliberation that produces the product's trust signal is also its cost driver. The industry has spent 2024–2026 attacking exactly this cost-quality trade-off, reporting 40–85% spend reductions from routing and adaptive compute, and the tooling has moved from research projects to commodity platform features (AWS Bedrock and Azure ship native prompt routers; OpenRouter rebuilt its auto-router in-house; open-source semantic routers reached production releases).

Three drivers make this review timely:

1. **Shipped-but-dormant capacity.** ADR-044 implemented the three biggest levers (performance-blended selection, early consensus termination, graduated depth) — all default-off or shadow-mode. The gap between what we built and what we run is currently larger than the gap between what we built and the state of the art.
2. **Market movement invalidating old assumptions.** Not Diamond — the vendor ADR-020 integrated — pivoted to coding-agent routing and was dropped from OpenRouter's auto-router; Portkey was acquired by Palo Alto Networks; hyperscalers now bundle routing free. Any strategy that outsources routing intelligence has aged badly; ADR-044's in-house call has aged well.
3. **New optimization axes we don't yet exploit.** The field now routes on dimensions we treat as fixed: reasoning-effort budgets, per-step (not per-query) decisions, cache affinity as a routing cost, and asymmetric model roles (cheap judges, expensive generators).

### Verdicts

| Question | Verdict |
|---|---|
| Replace the in-house strategy with an external router? | **No.** The market validated ADR-044's supersession of ADR-039/043. External routers solve single-model choice; the council needs auditable *portfolio* selection. |
| Update/improve? | **Yes — activate first, then sharpen.** Graduate the ADR-044 flags out of shadow mode; then contextual (per-domain) indexing, starting-rung prediction, classifier upgrade, and the new axes in §5. |
| Abstract/decouple as a separate product? | **Decouple internally; do not productize now.** The routing *mechanism* is commoditizing at every layer of the stack; the durable, differentiated asset is the **deliberation ground-truth index** — peer-reviewed quality data generated as exhaust. Formalize the internal boundary (cheap, preserves optionality), consume commodity layers deliberately, and define explicit triggers for extraction (§7). |

---

## 2. Method and scope

Two research passes were run. **Pass A** assessed the implemented strategy stack and its direct inheritors (routing surveys, cascade theory, ensemble stopping rules, router benchmarks). **Pass B** — added after recognizing Pass A's bias toward validating what we already ship — swept newly identified opportunity spaces: platform-native routing, preference-aligned/RL routers, per-step agentic routing, effort routing, cache-aware routing, SLM-first architectures, and the gateway market's consolidation (which feeds the build-vs-buy assessment in §7). Code assessment covered `tier_contract.py`, `triage/`, `metadata/selection.py`, `performance/`, `audition/`, `graduated_depth.py`, `early_consensus.py`, and the governing ADRs.

---

## 3. The routing estate today

| Layer | Mechanism | ADR | Status (Aug 2026) |
|---|---|---|---|
| L1 tier selection | Rule-based `TierContract` (quick/balanced/high/reasoning/frontier) | 022 | Live, default path |
| L2 triage | Keyword/length `HeuristicComplexityClassifier`; confidence-gated fast path; wildcard specialists; prompt optimization | 020 | Heuristics live; explicitly a placeholder |
| L2 external routing | Not Diamond API client (`triage/not_diamond.py`) | 020 | Off by default; **stale** — vendor pivoted, endpoints pre-date pivot, contains mock-response fallback |
| Candidate selection | Static registry scores + anti-herding penalty + diversity selection + dynamic discovery + circuit-breaker filtering | 026/028 | Live |
| Model lifecycle | Audition (SHADOW→FULL), graduation frontier→high, cost ceiling, voting authority | 027/029 | Live |
| Performance-aware selection | Live Borda/latency/cost index blended into scoring by confidence tier | 044 P1 | **Opt-in, default off** |
| Early consensus termination | Strict Borda-unassailability stopping rule in Stage 2 | 044 P2 | **Shadow mode default** |
| Graduated depth | Cascade single→mini(3)→full, prefix-superset model sets, consensus-gated escalation, budget veto | 044 P3 | **Opt-in; shadow telemetry wired v0.43 (#618/#622)** |
| Cost accounting | Ground-truth per-model cost, `quality_per_cost`, opt-in cost-aware ranking, budget enforcement | 011 | Live (accounting) / opt-in (influence) |
| Governance | Layer sovereignty, route receipts (`LayerEvent`s), offline mode | 024/026 | Live — a differentiator, see §7 |

**Structural read:** the estate is architecturally sound and unusually well-governed (route receipts and flag-gated influence are ahead of most commercial routers). Its two weaknesses are (a) the intelligence at L2 is 2025-era keyword heuristics, and (b) the highest-value machinery is switched off pending shadow-data review.

---

## 4. Landscape A — how our strategies and their inheritors fared

- **Compositional routing is the endorsed shape.** The field's definitive survey ([arXiv 2603.04445](https://arxiv.org/abs/2603.04445)) taxonomizes routing by *when* (pre-request / during / post-response), *what* (query features, metadata, past performance), and *how* (rules, classifiers, RL, cascades), and observes production systems are compositional. The L1–L4 + ADR-044 stack occupies all three *when* positions. No architectural correction needed.
- **Heterogeneous councils went mainstream.** [Council Mode](https://arxiv.org/html/2604.02923) (triage → parallel heterogeneous generation → structured consensus) and [AdaptOrch](https://arxiv.org/pdf/2602.16873) validate the core product architecture academically. [RouterEval](https://arxiv.org/abs/2503.10657)'s "model-level scaling" finding — routing gains grow with candidate-pool size and router quality — retroactively justifies discovery (ADR-028) and audition (ADR-029).
- **Cascade theory sharpened, in our favor and against.** [Is Escalation Worth It? (2605.06350)](https://arxiv.org/abs/2605.06350): cascades are limited by *structural cost* (the shallow pass is always paid) and a lightweight **pre-generation router often beats deferral cascades**; multi-stage chains underperform optimized pairs. Graduated depth partially dodges the critique (prefix-superset reuse means escalation only *adds* spend) but the lesson stands: predict the starting rung, don't always climb (→ R4).
- **Adaptive stopping validated, with headroom.** [DASE (2605.04236)](https://arxiv.org/abs/2605.04236) shows sequential evidence accumulation with *calibrated* commit signals stops earlier than strict rules and that adaptive stopping — not richer inter-agent communication — drives gains. Our unassailable-margin rule is the provably-safe end of this spectrum; shadow logs can quantify what a calibrated mode would add (→ R5).
- **The external-router bet we declined has been marked to market.** Not Diamond ($2.3M seed) pivoted to [Not Diamond Code](https://www.notdiamond.ai/blog/not-diamond-code-intelligent-model-routing-for-coding-agents); OpenRouter dropped it and rebuilt [`openrouter/auto`](https://openrouter.ai/docs/features/model-routing) on an in-house ~30-task-type classifier ranked by 7-day market spend. ADR-044's decision to supersede ADR-039/043 with an in-house index is confirmed.
- **Router evaluation standardized.** [RouterBench](https://arxiv.org/abs/2403.12031) / [LLMRouterBench](https://arxiv.org/pdf/2601.07206) evaluate on **cost-quality frontier curves**, not point metrics. Our bench matrix (solo/council/graduated over one dataset) is one reporting change away from this (→ R7).

---

## 5. Landscape B — newly identified opportunity space

This section corrects Pass A's bias: levers the industry now treats as first-class that our stack does not yet model.

### B1. Reasoning-effort as a routing axis
GPT-5-class systems route internally between fast and thinking variants with a real-time router, and expose `reasoning_effort` for programmatic trade-offs; adaptive thinking-budget work ([DART, 2606.23181](https://arxiv.org/pdf/2606.23181); [adaptive test-time allocation, 2604.14853](https://arxiv.org/abs/2604.14853)) shows per-query effort allocation beating uniform budgets by consistent margins. **Our gap:** `reasoning/` fixes effort per *tier and stage* (MINIMAL→XHIGH). Effort is a second routing dimension — (model, effort) per query, informed by the same complexity/consensus signals. This is cheaper to exploit than model switching: same model, same cache, smaller bill. *(→ R6)*

### B2. Asymmetric councils — route the reviewers, not just the members
Research extended routing to **each step** of agentic workflows, allocating strong models only to steps predicted hard ([explainable model routing for agentic workflows, 2604.03527](https://arxiv.org/html/2604.03527v1)). The council analog is that Stage 1 (generation), Stage 2 (judging), and Stage 3 (synthesis) are different tasks with different capability floors — yet we field the same members for generation and review. ADR-040 Option E ("tiered Stage 2") anticipated this and was deferred; the field has since supplied the evidence that judging is cheaper than generating. Cheap-judge configurations would cut the N-reviewer multiplier — the single largest structural cost after Stage 1 — and are directly measurable with the existing bias-audit machinery (reviewer calibration) as the safety check. *(→ R3)*

### B3. Cache affinity is a routing cost — selection stability matters
Infrastructure-level routing went cache-aware in 2026 ([llm-d](https://developers.redhat.com/articles/2025/10/07/master-kv-cache-aware-routing-llm-d-efficient-ai-inference), GKE Inference Gateway, NVIDIA Dynamo): a cache hit is ~10× cheaper, and routers now score *prefix affinity* per target. As an API consumer we see the same physics through prompt-cache pricing (ADR-049 already built stable prefixes + session affinity). **The new insight for us:** every routing decision that *changes* a model mid-session (per-round verify, graduated-depth escalation, per-domain reselection) silently forfeits cache discounts. Selection churn is a cost the router should price — a stickiness term using ADR-049's session telemetry. The per-step routing literature flags exactly this trade-off (switching interrupts prefill reuse and can offset the gains). *(→ R8)*

### B4. SLM-first economics for mechanical roles
NVIDIA's SLM-first position ([Belcak et al.](https://arize.com/blog/nvidias-small-language-models-are-the-future-of-agentic-ai-paper/)) — 10–30× cost advantage on narrow repetitive subtasks, escalate only hard turns — maps onto council substeps that need no frontier model: triage classification, style normalization (Stage 1.5), ranking parsing fallbacks, screening (ADR-047 P3). A local/quick-tier SLM for these keeps frontier spend where deliberation quality actually lives, and strengthens the offline story. *(→ R9)*

### B5. Preference-aligned and RL-trained routers
[Arch-Router (2506.16655)](https://arxiv.org/abs/2506.16655): a compact 1.5B self-hostable router mapping queries to a **natural-language domain-action taxonomy**, with a decoupled route→model table (change the pool without retraining). RL variants ([xRouter](https://arxiv.org/pdf/2510.08439), [SeqRoute](https://arxiv.org/pdf/2605.25424)) optimize cost-aware policies end-to-end. **Relevance:** the Arch-Router *pattern* — policy taxonomy in config, tiny local model for matching, mapping table owned by us — is the right successor to the keyword heuristic, and fits sovereignty (self-hosted weights) better than an API. [vLLM Semantic Router](https://blog.vllm.ai/2026/01/05/vllm-sr-iris.html) (Apache-2.0, ModernBERT classifiers, intent/complexity/safety signals) is the packaged open-source alternative. *(→ R2)*

### B6. Platform-native routing (the consume side)
[AWS Bedrock Intelligent Prompt Routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html) (GA, claims ~60% savings), [Azure AI Foundry model router](https://www.llmreference.com/router/bedrock-intelligent-prompt-routing), and OpenRouter auto/auto-beta make single-model routing a **free platform feature**. None of them select portfolios, honor diversity/anti-herding constraints, or emit route receipts — so none can replace L2/L3 — but they are legitimate *pool entries* (a tier can include `openrouter/auto` as one member) and they anchor the build-vs-buy analysis in §7.

### B7. The supervision-signal scarcity — our hidden asset
Every router's binding constraint is *training/steering signal*: OpenRouter uses market spend (popularity proxy), RouteLLM used arena preferences (generic), Not Diamond curated evals (expensive), and current research works on inferring [capability distributions from sampled outcomes](https://arxiv.org/pdf/2606.06924) and [dueling feedback](https://arxiv.org/pdf/2510.00841) precisely because per-request quality labels are scarce. **The council generates per-session, task-local, anonymized peer-review quality measurements as exhaust.** This reframes the performance index from "a routing input" to "the scarce asset in the routing economy" — central to §7.

---

## 6. Recommendation register

| # | Recommendation | Type | Effort | Impact | Depends on |
|---|---|---|---|---|---|
| R1 | **Activate ADR-044**: review shadow telemetry; flip `LLM_COUNCIL_EARLY_CONSENSUS`, then performance selection, then graduated depth | Activate | S | **High** — the field's 40–85% savings live behind these flags | Shadow data volume |
| R2 | **Replace the heuristic classifier** with a self-hosted taxonomy router (Arch-Router pattern or vLLM SR classifiers); keep heuristics as offline fallback | Improve | M–L | High | — |
| R3 | **Asymmetric councils** (revive ADR-040 Option E): cheap-judge Stage 2 configurations, validated via bench + reviewer-calibration bias audit | New | M | **High** — attacks the N-reviewer multiplier | R7 for measurement |
| R4 | **Starting-rung prediction** for graduated depth: predicted-complex queries start at full council (pre-generation routing beats pure deferral) | Improve | S–M | Medium | R2 signal quality |
| R5 | **Calibrated early-consensus mode** (DASE-style) as a second, opt-in stopping rule once shadow logs quantify the conservatism gap | Improve | M | Medium | R1 data |
| R6 | **Effort routing**: make `reasoning_effort` a per-query routed dimension, not a tier constant | New | M | Medium-High — cheapest compute lever (no cache loss) | — |
| R7 | **Bench frontier curves**: RouterBench-style cost-quality frontier reporting in `bench/matrix.py` | Improve | S | Medium — makes every other decision measurable | — |
| R8 | **Cache-affinity stickiness term** in selection: price model-switching's forfeited cache discounts using ADR-049 telemetry | New | S–M | Medium | — |
| R9 | **SLM utility roles**: local/quick-tier models for triage, normalization, parsing, screening | New | M | Medium | — |
| R10 | **ADR-020 amendment**: retire the Not Diamond integration (superseded by ADR-044); note platform auto-routers as ordinary pool entries; delete `_mock_response` dead path | Housekeeping | S | Low (hygiene, honesty of the estate) | — |
| R11 | **Contextual index**: key `ModelPerformanceIndex` by triage domain (per-domain Borda, existing confidence-tier gating per cell) | Improve | M | High — the industry's clearest structural lead over us | Traffic volume per cell |

**Not recommended:** adopting an external learned router as selection authority (breaks sovereignty/auditability/offline, and no product routes portfolios); extending the cascade beyond three rungs (theory says k-stage chains underperform); per-reviewer randomization-style complexity without measurement (see ADR-017 Amendment 1 precedent).

---

## 7. Strategic assessment — should routing be a separate product?

### 7.1 Decompose before deciding

"The routing capability" is six distinct things with different market positions:

| Capability | Ours | Market status | Class |
|---|---|---|---|
| A. Query understanding / triage | Heuristics (weak) | Free, open weights (ModernBERT, Arch-Router 1.5B), platform-bundled | **Commodity — consume** |
| B. Single-model routing | Fast path | Free at three layers: in-model (GPT-5 router), platform (Bedrock/Azure/OpenRouter), gateway (LiteLLM/Bifrost) | **Commodity — consume** |
| C. Portfolio (council) selection — diversity, anti-herding, audition lifecycle | `metadata/selection.py`, ADR-029 | **Unserved.** Every product routes to *one* model; ensemble selection lives only in papers | **Differentiated — build** |
| D. Adaptive deliberation depth & stopping | ADR-044 P2/P3 | Active research (DASE, cascade theory); no product | **Differentiated — build** |
| E. Deliberation ground-truth index | `performance/` + Borda exhaust | **Scarce everywhere** (§5 B7): competitors use popularity or arena proxies | **Differentiated — the asset** |
| F. Route governance — receipts, sovereignty, offline | LayerEvents, ADR-024 | Emerging enterprise requirement; gateways bolt on observability, none audit routing *influence* | **Differentiated — build** |

### 7.2 Market evidence on productizing

The standalone-router business thesis is being falsified in real time:

- **Absorption from below:** hyperscalers ship routing free (Bedrock GA since April 2025, Azure Foundry native). When the platform bundles your product as a feature, standalone pricing power collapses.
- **Absorption from above:** frontier vendors internalize routing into the model itself (GPT-5's real-time router, effort parameters). The middleware is squeezed from both ends.
- **The cohort:** Not Diamond ($2.3M) pivoted to a coding-agent niche after losing its OpenRouter placement; [Martian](https://tracxn.com/d/companies/martian/__tQy9XwPRiABRLG8-5nz_kMJUZpikAlCbFUav00kumYM) (~$9–32M raised) survives via enterprise interpretability positioning; [Portkey exited via acquisition](https://www.pkgpulse.com/guides/portkey-vs-litellm-vs-openrouter-llm-gateway-2026) into Palo Alto's security suite. The 2026 gateway-market consensus is explicit: *the gateway is commoditizing; differentiation is moving up-stack into evaluation and observability* — i.e., toward capability E/F, not B.
- **The data problem:** a hosted router product needs cross-tenant signal aggregation at volume. Our index's confidence gating (≥10/30/100 sessions *per model per tenant*) is honest about this: the flywheel is tenant-local. We do not have — and as an OSS project should not want — the centralized traffic that makes a learned-router service defensible.

### 7.3 Options and cost-benefit

**Option 1 — Status quo (embedded, no change).** Cost ≈ 0. Forgoes nothing functionally; forgoes optionality and clarity.

**Option 2 — Internal decoupling ("routing kernel").** Formalize C+D+E+F behind a documented, stable sub-API inside the package (the ADR-024 layer contracts already do ~80% of this; remaining work is interface hygiene between `triage/`, `metadata/`, `performance/`, `graduated_depth.py`). Cost: small, one refactor epic. Benefit: testability, honest seams for consuming commodity components (swap classifiers without touching council code), and **free optionality** — extraction later becomes a packaging exercise, not surgery. *No second release train, no split test matrix.*

**Option 3 — Extract an OSS library now (`council-routing`).** Cost: real and recurring — second release/versioning/docs/DoD burden on a project whose Definition of Done already includes a docs site; and the extracted library would ship the *mechanism without the signal* (the index is empty without deliberation traffic), so standalone value is weak. Benefit: an adoption channel — but llm-council itself already is one.

**Option 4 — Standalone product/SaaS.** Cost: everything in Option 3 plus cross-tenant data machinery, consent/privacy expansion, and a sales motion — into a market where the incumbent price is **$0** and the exits are acqui-absorptions. Against: every datapoint in §7.2. The only fragment with genuine product logic is **E as a data product** ("continuously refreshed model-quality rankings from adversarial peer review" — an always-fresh arena) — and ADR-048's bench publication already provides a zero-commitment version of that surface.

**Decision: Option 2.** Build the differentiated layer (C/D/E/F), consume the commodity layers (A components as vendored open weights; B as optional pool entries and gateway features), decouple internally for optionality, and decline to productize.

### 7.4 Revisit triggers

Re-open the productization question if **any** of:

1. **External pull:** recurring user requests to use the selection/index machinery *without* running councils (issues, discussions, forks extracting `metadata/`).
2. **Measured edge:** bench frontier curves (R7) show the deliberation-ground-truth index beating market-spend/task-type routing by a margin worth naming publicly.
3. **Volume:** council traffic pushes many models to HIGH-confidence index tiers, making the tenant-local flywheel demonstrably self-sustaining — the precondition any extracted artifact needs.
4. **Market gap persists:** by mid-2027 no product serves portfolio selection for multi-model deliberation (the C+D niche stays empty while multi-agent adoption grows).

### 7.5 Risk to the whole strategy: model convergence

AdaptOrch's premise — an "era of LLM performance convergence" — is the bear case for *all* quality-based routing: if frontier models converge, routing value collapses into cost/latency arbitrage, favoring dumb-simple cost tiers over sophisticated quality indexes. Partial hedge: the council's purpose is *verification confidence*, where model diversity retains value even under capability convergence (uncorrelated errors, not capability gaps, are what peer review exploits). But this argues for keeping routing investment **proportional and incremental** (the R-register's S/M efforts) rather than betting big on routing sophistication.

---

## 8. Sequencing

1. **Now (activation & hygiene):** R1 shadow-data review → flag flips; R10 ADR-020 amendment; R7 bench frontier curves.
2. **Next (the contextual-routing epic — candidate ADR-055):** R11 domain-keyed index, R4 starting-rung prediction, R2 classifier upgrade — one coherent epic, each independently shippable behind flags per house style.
3. **Then (new axes):** R3 asymmetric councils (needs R7 to measure), R6 effort routing, R8 cache-stickiness term, R9 SLM utility roles.
4. **Parallel (strategic):** Option 2 internal decoupling folded into the ADR-055 epic's refactoring budget; §7.4 triggers reviewed at each release retro.

---

## 9. Sources

**Surveys & theory:** [Dynamic Model Routing and Cascading: A Survey (2603.04445)](https://arxiv.org/abs/2603.04445) · [Is Escalation Worth It? (2605.06350)](https://arxiv.org/abs/2605.06350) · [DASE: Adaptive Consensus via Sequential Evidence Accumulation (2605.04236)](https://arxiv.org/abs/2605.04236) · [Adaptive Test-Time Compute Allocation (2604.14853)](https://arxiv.org/abs/2604.14853) · [DART: Adaptive Thinking Budgets (2606.23181)](https://arxiv.org/pdf/2606.23181) · [From Sampled Outcomes to Capability Distributions (2606.06924)](https://arxiv.org/pdf/2606.06924) · [LLM Routing with Dueling Feedback (2510.00841)](https://arxiv.org/pdf/2510.00841)

**Routers & systems:** [Arch-Router (2506.16655)](https://arxiv.org/abs/2506.16655) · [xRouter (2510.08439)](https://arxiv.org/pdf/2510.08439) · [SeqRoute (2605.25424)](https://arxiv.org/pdf/2605.25424) · [vLLM Semantic Router v0.1 Iris](https://blog.vllm.ai/2026/01/05/vllm-sr-iris.html) · [Red Hat on vLLM SR](https://www.redhat.com/en/blog/bringing-intelligent-efficient-routing-open-source-ai-vllm-semantic-router) · [OpenRouter model routing docs](https://openrouter.ai/docs/features/model-routing) · [AWS Bedrock Intelligent Prompt Routing](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-routing.html) · [Explainable Model Routing for Agentic Workflows (2604.03527)](https://arxiv.org/html/2604.03527v1) · [llm-d cache-aware routing](https://developers.redhat.com/articles/2025/10/07/master-kv-cache-aware-routing-llm-d-efficient-ai-inference)

**Benchmarks:** [RouterBench (2403.12031)](https://arxiv.org/abs/2403.12031) · [RouterEval (2503.10657)](https://arxiv.org/abs/2503.10657) · [LLMRouterBench (2601.07206)](https://arxiv.org/pdf/2601.07206) · [RouteJudge (2606.18774)](https://arxiv.org/pdf/2606.18774)

**Multi-agent:** [Council Mode (2604.02923)](https://arxiv.org/html/2604.02923) · [AdaptOrch (2602.16873)](https://arxiv.org/pdf/2602.16873) · [AgentRouter (ACL 2026)](https://aclanthology.org/2026.acl-long.33/)

**Market:** [Not Diamond Code launch](https://www.notdiamond.ai/blog/not-diamond-code-intelligent-model-routing-for-coding-agents) · [Not Diamond profile (Tracxn)](https://tracxn.com/d/companies/not-diamond/__-ifpQNdltj98K5h7wki2GzegvCScnOt_vhbDrwaZaA0) · [Martian profile (Tracxn)](https://tracxn.com/d/companies/martian/__tQy9XwPRiABRLG8-5nz_kMJUZpikAlCbFUav00kumYM) · [Portkey→Palo Alto / gateway landscape (PkgPulse)](https://www.pkgpulse.com/guides/portkey-vs-litellm-vs-openrouter-llm-gateway-2026) · [Gateway comparison (Maxim)](https://www.getmaxim.ai/articles/openrouter-vs-litellm-vs-bifrost-ai-gateway-comparison/) · [Braintrust: Best LLM routers 2026](https://www.braintrust.dev/articles/best-llm-routers-2026) · [Kosmoy: 2026 gateway trends](https://www.kosmoy.com/resources/blog/6-ai-gateway-trends-that-will-shape-2026/) · [NVIDIA SLM-first thesis (Arize summary)](https://arize.com/blog/nvidias-small-language-models-are-the-future-of-agentic-ai-paper/)
