# Adaptive Consensus in LLM Ensembles via Sequential Evidence Accumulation: Automatic Budget Identification and Calibrated Commit Signals

**Source:** https://arxiv.org/abs/2605.04236
**Added:** 2026-08-23
**Tags:** #unsorted

---

> Large Language Model ensembles improve reasoning accuracy, but only up to a performance boundary beyond which additional deliberation degrades accuracy. We introduce DASE (Deliberative Adaptive Stopping Ensemble), a stopping heuristic for iterative ensemble deliberation that commits early on genuine consensus and applies a global-frequency fallback on fragmented evidence. We make three contributions. (1) DASE produces a commit-type routing partition that generalises across benchmarks and is complementary to verbalized single-call confidence. On GPQA-Extended (N=546, 70B ensemble), the partition yields a 39.5 pp routing gap (right-wall 81.1% vs. left-wall 41.5%). On AIME 2010-2023 (N=261, 120B ensemble, 3 seeds), right-wall commits reach 98.3% accuracy vs. left-wall 72.8% (25.5 pp gap), statistically equivalent to Opus 4.6 Standard verbalized confidence at matched coverage (25.7 pp gap; bootstrap p=0.873); the two mechanisms disagree on 37% of routing assignments. (2) Adaptive stopping, not injection bandwidth, drives accuracy. On AIME-300, bandwidth accounts for only 0.3 pp (ns). On GPQA-Extended at the 120B tier, sparse injection ($\approx15$ tokens/worker/round) achieves 70.9% with a 30.7 pp routing gap; dense injection ($\approx600$ chars/worker/round) achieves 72.2% but with halved right-wall coverage and a narrower 18.9 pp gap. (3) Injection-based methods exhibit an inverted-U accuracy-vs-inference trajectory; this pattern is hypothesis-generating.

---

[View PDF](https://arxiv.org/pdf/2605.04236) [HTML (experimental)](https://arxiv.org/html/2605.04236v2)

> Abstract:Large Language Model ensembles improve reasoning accuracy, but only up to a performance boundary beyond which additional deliberation degrades accuracy. We introduce DASE (Deliberative Adaptive Stopping Ensemble), a stopping heuristic for iterative ensemble deliberation that commits early on genuine consensus and applies a global-frequency fallback on fragmented evidence. We make three contributions. (1) DASE produces a commit-type routing partition that generalises across benchmarks and is complementary to verbalized single-call confidence. On GPQA-Extended (N=546, 70B ensemble), the partition yields a 39.5 pp routing gap (right-wall 81.1% vs. left-wall 41.5%). On AIME 2010-2023 (N=261, 120B ensemble, 3 seeds), right-wall commits reach 98.3% accuracy vs. left-wall 72.8% (25.5 pp gap), statistically equivalent to Opus 4.6 Standard verbalized confidence at matched coverage (25.7 pp gap; bootstrap p=0.873); the two mechanisms disagree on 37% of routing assignments. (2) Adaptive stopping, not injection bandwidth, drives accuracy. On AIME-300, bandwidth accounts for only 0.3 pp (ns). On GPQA-Extended at the 120B tier, sparse injection ($\\approx15$ tokens/worker/round) achieves 70.9% with a 30.7 pp routing gap; dense injection ($\\approx600$ chars/worker/round) achieves 72.2% but with halved right-wall coverage and a narrower 18.9 pp gap. (3) Injection-based methods exhibit an inverted-U accuracy-vs-inference trajectory; this pattern is hypothesis-generating.

Subjects:

Machine Learning (cs.LG)

Cite as:

[arXiv:2605.04236](https://arxiv.org/abs/2605.04236) \[cs.LG\]

 

(or [arXiv:2605.04236v2](https://arxiv.org/abs/2605.04236v2) \[cs.LG\] for this version)

 

[https://doi.org/10.48550/arXiv.2605.04236](https://doi.org/10.48550/arXiv.2605.04236)

arXiv-issued DOI via DataCite

## Submission history

From: Roberto Medina PhD \[[view email](https://arxiv.org/show-email/f3593f09/2605.04236)\]  
**[\[v1\]](https://arxiv.org/abs/2605.04236v1)** Tue, 5 May 2026 19:24:10 UTC (611 KB)  
**\[v2\]** Thu, 14 May 2026 11:54:24 UTC (847 KB)
