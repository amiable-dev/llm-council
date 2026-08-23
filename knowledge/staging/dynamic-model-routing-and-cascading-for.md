# Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey

**Source:** https://arxiv.org/abs/2603.04445
**Added:** 2026-08-23
**Tags:** #unsorted

---

> The rapid growth of large language models (LLMs) with diverse capabilities, costs, and domains has created a critical need for intelligent model selection at inference time. While smaller models suffice for routine queries, complex tasks demand more capable models. However, static model deployment does not account for the complexity and domain of incoming queries, leading to suboptimal performance and increased costs. Dynamic routing systems that adaptively select models based on query characteristics have emerged as a solution to this challenge.
  We provide a systematic analysis of state-of-the-art multi-LLM routing and cascading approaches. In contrast to mixture-of-experts architectures, which route within a single model, we study routing across multiple independently trained LLMs. We cover diverse routing paradigms, including query difficulty, human preferences, clustering, uncertainty quantification, reinforcement learning, multimodality, and cascading. For each paradigm, we analyze representative methods and examine key trade-offs. Beyond taxonomy, we introduce a conceptual framework that characterizes routing systems along three dimensions: when decisions are made, what information is used, and how they are computed. This perspective highlights that practical systems are often compositional, integrating multiple paradigms under operational constraints.
  Our analysis demonstrates that effective multi-LLM routing requires balancing competing objectives. Choosing the optimal routing strategy depends on deployment and computational constraints. Well-designed routing systems can outperform even the most powerful individual models by strategically leveraging specialized capabilities across models while maximizing efficiency gains. Meanwhile, open challenges remain in developing routing mechanisms that generalize across diverse architectures, modalities, and applications.

---

[View PDF](https://arxiv.org/pdf/2603.04445) [HTML (experimental)](https://arxiv.org/html/2603.04445v2)

> Abstract:The rapid growth of large language models (LLMs) with diverse capabilities, costs, and domains has created a critical need for intelligent model selection at inference time. While smaller models suffice for routine queries, complex tasks demand more capable models. However, static model deployment does not account for the complexity and domain of incoming queries, leading to suboptimal performance and increased costs. Dynamic routing systems that adaptively select models based on query characteristics have emerged as a solution to this challenge.  
> We provide a systematic analysis of state-of-the-art multi-LLM routing and cascading approaches. In contrast to mixture-of-experts architectures, which route within a single model, we study routing across multiple independently trained LLMs. We cover diverse routing paradigms, including query difficulty, human preferences, clustering, uncertainty quantification, reinforcement learning, multimodality, and cascading. For each paradigm, we analyze representative methods and examine key trade-offs. Beyond taxonomy, we introduce a conceptual framework that characterizes routing systems along three dimensions: when decisions are made, what information is used, and how they are computed. This perspective highlights that practical systems are often compositional, integrating multiple paradigms under operational constraints.  
> Our analysis demonstrates that effective multi-LLM routing requires balancing competing objectives. Choosing the optimal routing strategy depends on deployment and computational constraints. Well-designed routing systems can outperform even the most powerful individual models by strategically leveraging specialized capabilities across models while maximizing efficiency gains. Meanwhile, open challenges remain in developing routing mechanisms that generalize across diverse architectures, modalities, and applications.

Comments:

Work funded by ADAPT Centre, Trinity College Dublin, and Huawei Ireland

Subjects:

Networking and Internet Architecture (cs.NI); Computation and Language (cs.CL); Performance (cs.PF)

Cite as:

[arXiv:2603.04445](https://arxiv.org/abs/2603.04445) \[cs.NI\]

 

(or [arXiv:2603.04445v2](https://arxiv.org/abs/2603.04445v2) \[cs.NI\] for this version)

 

[https://doi.org/10.48550/arXiv.2603.04445](https://doi.org/10.48550/arXiv.2603.04445)

arXiv-issued DOI via DataCite

## Submission history

From: Yasmin Moslem \[[view email](https://arxiv.org/show-email/26ab791a/2603.04445)\]  
**[\[v1\]](https://arxiv.org/abs/2603.04445v1)** Mon, 23 Feb 2026 21:57:27 UTC (2,637 KB)  
**\[v2\]** Tue, 21 Apr 2026 10:38:10 UTC (2,650 KB)
