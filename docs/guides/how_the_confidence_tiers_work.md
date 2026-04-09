# Council Confidence Tiers

The difference between the tiers is essentially a trade-off between **certainty (Consensus)** and **speed (Latency)**.

Per the orchestration logic in `tier_contract.py`, the council changes its entire "personality" based on the tier you select:

### ⚡ `quick` Tier (The "Sprint")
*   **No Voting**: The council skips Stage 2 entirely to save time.
*   **The Workflow**: Every model in the pool (e.g., GPT-5-mini, Haiku-4.5, Qwen-Turbo) generates its response in parallel.
*   **The "Verifier"**: Instead of a peer-review session, it uses a lightweight verifier. A single fast model performs a "gut check" for hallucinations or refusals, and then the Chairman (Gemini 3.1 Pro) immediately synthesizes the answer.
*   **Ideal for**: Facts, code snippets, or simple explanations where you just want a second and third opinion without a debate.

### ⚖️ `balanced` Tier (The "Jury")
*   **Full Peer Review**: Peer review is active.
*   **The Workflow**: After models generate responses (Stage 1), they are anonymized (Stage 1.5) and sent back to each other. Every model must rank and score its peers' work (Stage 2).
*   **Consensus-Driven**: The Chairman receives a **Borda Count** (a mathematical ranking) of which models were voted "best" by their peers and uses that to weigh the final answer.
*   **Ideal for**: Technical comparisons, complex trade-offs, or open-ended advice where you want the "wisdom of the crowd" to filter out low-quality answers.

### 🏛️ `high` Tier (The "Congress")
*   **Maximum Rigor**: Similar to balanced, but with much stricter timeouts and quality thresholds.
*   **The Model Pool**: While `quick` uses "Economy" models (Turbo/mini/Haiku), the `high` tier uses "Frontier" models (Opus 4.6, GPT-5.4, Gemini 3.1 Pro) for all three stages.
*   **Triple-Check**: It has `max_attempts: 3`, meaning if the models disagree too wildly or the verifier fails, the council can actually retry or escalate the deliberation.
*   **Ideal for**: High-stakes decisions, complex architectural reviews, or anything where an error would be costly.

### 🧠 `reasoning` Tier (The "Think Tank")
*   **Deep Deliberation**: Specifically designed for models with internal "Chain of Thought" (CoT) capabilities (e.g., o1, o3, DeepSeek-R1).
*   **The Workflow**: Since these models are slower and generate much more text, the council provides a massive **10-minute time budget**. It also increases the token limit to **8,192** to prevent truncation of long reasoning paths.
*   **Expert Synthesis**: Uses **Claude Opus 4.6** as the Chairman, which is tuned to weigh the logical consistency of reasoning outputs more heavily than the other tiers.
*   **Ideal for**: Solving complex math/logic puzzles, deep architectural debugging, or multi-step strategic planning.

## Comparison Table

| Feature | `quick` | `balanced` | `high` | `reasoning` |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 2 (Voting)** | **No** | **Yes** | **Yes** | **Yes** |
| **Peer Ranking** | None | Borda Count | Borda Count + Detail | Comprehensive |
| **Model Class** | Economy (Turbo/Flash) | Standard (Pro) | Frontier (Opus/GPT-5) | Reasoning (o1/R1) |
| **Global Deadline** | 30 seconds | 90 seconds | 180 seconds | 600 seconds |
| **Chairman Role** | Summarizer | Mediator | Lead Synthesizer | Logical Auditor |

!!! tip "Pro-tip"
    You can see this in action by asking the council for something complex (like "Explain Quantum Physics") using `tier="quick"` and then again with `tier="high"`. In the latter, you'll see a `### Council Rankings` section appear because the voting stage was activated!
