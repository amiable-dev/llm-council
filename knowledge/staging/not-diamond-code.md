# Not Diamond Code: intelligent model routing for coding agents

**Source:** https://www.notdiamond.ai/blog/not-diamond-code-intelligent-model-routing-for-coding-agents
**Added:** 2026-08-23
**Tags:** #unsorted

---

> Not Diamond Code routes each coding-agent step to the best model and reasoning effort, helping teams reduce inference costs by 20%+ without degrading quality.

---

Today we are announcing Not Diamond Code, our intelligent model router for long-horizon coding agents. Not Diamond Code integrates with any gateway and agent harness, including Claude Code, to automatically select the best model at the lowest cost for each step in an agent session, reducing costs by 20%+ without any degradation in quality.

Inference spend has increased dramatically in the past six months as individual developers and enterprises have adopted long-running, highly parallelized agentic workloads. Intelligent model routing allows teams to continuously benefit from rapidly improving capabilities, efficiency, and diversity in the model landscape to achieve lower costs and higher quality than any single model can provide.

Not Diamond Code is based on a novel routing technique that makes recommendations by predicting future rewards and costs for a given model and reasoning effort at each step of an agent sequence. Recommendations are made in a cache-aware manner that optimizes for long-trajectory outcomes and continuously updates in real-time based on developer feedback signals. We achieve optimal performance on the Pareto frontier across frontier coding agent benchmarks, and in our enterprise early access program we achieve savings of 20%+ while improving developer experience and satisfaction.

## Benchmark performance

We evaluated Not Diamond Code on Poly-SWE-bench, a multi-language repository-level benchmark of GitHub issues, and LongCodeQA, a long-context code comprehension benchmark over real-world repositories. We ran our evaluations with Claude Code as the harness routing between Haiku 4.5, Sonnet 4.6, and Opus 4.8 at various reasoning effort levels. We compare Not Diamond’s router performance against fixed Anthropic model and reasoning-effort configurations with respect to task completion rates and inference cost per task.

![Scatter plot comparing model-routing quality and cost on Poly-SWE-bench. Not Diamond Code appears on the Pareto frontier, achieving near-Opus 4.8 XHigh performance at substantially lower cost.](https://cdn.sanity.io/images/tz56nmh3/production/375e4185225233eca7cd739011c236995a59da50-1568x1127.png)

On Poly-SWE-Bench Verified, Not Diamond Code approximates Opus 4.8 Xhigh performance while reducing inference costs by 39%

![Scatter plot comparing model-routing quality and cost on LongCodeQA. Not Diamond Code reaches the Pareto frontier, delivering frontier-level code-comprehension performance with lower inference cost than fixed high-end model configurations.](https://cdn.sanity.io/images/tz56nmh3/production/fc162b34d4021843868b3b3ef69692d29b41872d-1568x1127.png)

On LongCodeQA, Not Diamond Code approximates Opus 4.8 Xhigh performance while reducing inference costs by 61%

Not Diamond Code achieves Pareto-optimal performance across both benchmarks, approximating the quality of Opus 4.8 Xhigh at a 39-61% cost reduction by routing each turn in the coding agent session to the best-suited model and reasoning effort.

We also evaluated routing between a mix of closed-source and open-source models, specifically Haiku 4.5, Sonnet 4.6, Opus 4.8, GLM 5.2, and DeepSeek V4 Flash on Poly-SWE-Bench. We show that introducing open weight models into the routing pool improves performance by 3.6% and increases cost savings from 39% to 66%.

![Scatter plot comparing routing performance and cost on SWE-PolyBench with Anthropic and open-source models. Adding GLM 5.2 and DeepSeek V4 Flash improves performance and increases cost savings compared with Anthropic-only routing.](https://cdn.sanity.io/images/tz56nmh3/production/e93a68ef3a1343a4901b5d1acaf572a6a6318d37-1566x1127.png)

Routing across both closed-source and open-source models improves Poly-SWE\_Bench performance by 3.6% and increases savings from 39% to 66%.

While significant cost savings can be achieved by routing within a single provider, the greatest opportunity is in routing between multiple providers and both closed-source and open-source models. This not only maximizes performance and cost savings for teams, but it also protects them from vendor lock-in and ensures they’re always benefitting from improvements in the model landscape.

## How Not Diamond Code works

Coding agent workloads span many user and subagent turns, and the optimal model choice can change throughout a session. Before each turn, Not Diamond considers the current and previous session states, message and token counts, task complexity, implicit developer feedback signals, and the state of the KV cache to model the future cost and future reward of a given model and reasoning effort recommendation. Our router then selects models to optimize for total session quality and cost outcomes rather than the quality and cost of the next request alone.

Not Diamond is cache-aware and accounts for the cost of switching models mid-session while the cache is warm. Accordingly, Not Diamond may stay on a more expensive model to preserve a warm cache even when a cheaper model is capable of handling a particular turn, or it may break cache to upgrade to a more capable model when that model is likely to complete the work more effectively or efficiently. Conversely, when context window utilization is low or the cache is cold, Not Diamond will prioritize routing economics over cache economics.

![Architecture diagram showing Not Diamond Code running as a local proxy alongside a coding-agent harness. The proxy sends derived metadata to the Not Diamond optimization service, receives a model-routing recommendation, and routes the request through the user’s existing gateway or provider.](https://cdn.sanity.io/images/tz56nmh3/production/594180270ddfad84da87243f09f54f12ccd32c7a-1953x917.png)

Not Diamond Code routes coding-agent requests through a privacy-preserving local proxy

Not Diamond Code runs through a privacy-preserving local proxy alongside a developer’s coding harness. The proxy collects anonymized, derived metadata from the agent payload and passes this metadata through to the Not Diamond optimization service, which returns a model and reasoning-effort recommendation to the local proxy. The request is then executed directly from the user’s machine through their existing gateway or provider, which makes Not Diamond the only intelligent model router that is harness- and gateway-agnostic. Additionally, this architecture enables Not Diamond to route in a privacy-preserving manner using only derived metadata, without ever requiring agent payloads, inputs, or outputs, to leave a developer’s local machine.

For a developer, their experience using Not Diamond Code remains exactly the same as when using their harness normally, with routing decisions being made automatically in the background. Not Diamond Code will also adapt over time based on each developer’s implicit feedback signals, improving continuously to personalize routing decisions to each developer’s workloads and preferences.

## Building the multi-model future

We founded Not Diamond to build the routing infrastructure for the multi-model future. A world with many diverse models is more performant and cost-efficient than one in which everyone uses a single giant model for everything. Intelligent model routing promotes a diverse market of providers, shifts the locus of power from labs to consumers, and reduces the ecological impact of AI. Eventually, we believe model routing will not only help with selecting between various generalist models, but also with routing between increasingly specialized small models.

In December 2023 we released the world’s first open source intelligent model router, and we have been working on this problem ever since. Model routing is both a deceptively difficult problem and a constantly moving target. For long-horizon coding agents, the interdependent variables and downstream consequences of model selection makes the problem even more challenging. As the vast majority of all inference spend shifts to agentic workloads, it is more important than ever to have effective, reliable, and secure routing infrastructure for every AI product and consumer.

Not Diamond Code is being used by leading startup and Fortune 500 engineering teams to reduce their inference spend while achieving the output quality and developer experience of the frontier. In our early access program, we see cost savings of of over 20% and increased developer experience metrics of 33% relative to Opus 4.8. Not Diamond is designed for enterprise deployments with SOC 2 compliance and ISO 27001 certification, privacy-preserving routing, harness- and gateway-agnostic integrations, granular cost and savings dashboards, and admin-level access and security controls.

## Apply for early access

We are selectively onboarding teams to Not Diamond Code early access. Developers and teams can test Not Diamond on their own coding-agent workflows and compare routing against their current default-model strategy. [Request access here](https://www.notion.so/361c0792ca6e804d993cd2142641c883?pvs=21), or [book time with our team](https://calendly.com/not-diamond-gtm/intro-from-nd-code-launch-blogpost).
