# How the LLM Council Works

The LLM Council is a sophisticated multi-stage deliberation system designed to produce high-quality, verified AI guidance. Unlike individual LLMs that can hallucinate or personal "favorites" that can be biased, the Council uses a **structured parliamentary process** to ensure every answer is peer-reviewed and synthesized for accuracy.

Here is the step-by-step lifecycle of a Council query.

```text
            [ USER QUERY ]
                  |
                  v
  +--------------------------------+
  |   STAGE 1: PARALLEL IDEATION   |  <-- Original responses created
  |                                |      in isolated silos
  | [A-GPT] [B-Claude] [C-Gemini]  |
  +--------------------------------+
                  |
                  v
  +--------------------------------+
  |   STAGE 1.5: NORMALIZATION     |  <-- Optional: Style rewritten
  |                                |      to hide "brand accents"
  |         [A] [B] [C]            |
  +--------------------------------+
                  |
                  v
  +--------------------------------+
  |   STAGE 2: BLIND PEER REVIEW   |  <-- Each model judges the answers (A/B/C)
  |                                |      without knowing the creators
  | [Judge A] -> [Ans B] & [Ans C] |  <-- A Borda Score is calculated for
  | [Judge B] -> [Ans A] & [Ans C] |      each model and the answers are ranked
  | [Judge C] -> [Ans A] & [Ans B] |
  +--------------------------------+
                  |
                  v
  +--------------------------------+
  |   STAGE 3: CHAIRMAN VERDICT    |  <-- Final editor (a frontier model)
  |                                |      reviews the answers + scores
  | [A-GPT] [B-Claude] [C-Gemini]  |
  |  [Rankings] + [Borda Scores]   |
  |                                |
  |    [Chairman (Synthesizer)]    |
  +--------------------------------+
                  |
                  v
           [ FINAL ANSWER ]
```

---

## The 3-Stage Deliberation Process

### Stage 1: Parallel Ideation (The Brainstorm)
When you submit a query, the Council simultaneously broadcasts your question to a pool of diverse LLMs (the "Council Members").
*   **Diverse Perspectives**: Depending on your tier (`quick`, `balanced`, or `high`), the system calls models from different providers (OpenAI, Anthropic, Google, Meta).
*   **Independent Thinking**: Each model generates its own answer in isolation, with no knowledge of what the other models are saying. This prevents "groupthink" at the earliest stage.

### Stage 1.5: Style Normalization (Optional)
To ensure the next stage is truly merit-based, the Council can optionally "mask" the voices of the models.
*   **Voice Masking**: A neutral model rewrites all Stage 1 responses into a standard, objective style.
*   **Anti-Fingerprinting**: This strips away stylistic signatures (like a specific model's favorite way of using bullet points) before the peer review begins.

### Stage 2: Anonymized Peer Review (The Debate)
This is the heart of the Council’s intelligence. Each Council Member is given the answers from all their peers.
*   **Blind Judging**: The responses are anonymized as **Ans A**, **Ans B**, and **Ans C**. The models do not know which company built which response.
*   **Strict Evaluation**: Every model acts as a "judge" (e.g., **Judge A**), evaluating its peers based on a structured rubric (Accuracy, Relevance, Completeness).
*   **Borda Score Rankings**: Models rank the responses from best to worst. The system then calculates a **Borda Score** (a weighted consensus ranking) to determine which answers actually stood up to peer scrutiny.

### Stage 3: Chairman's Verdict (The Synthesis)
Finally, a high-intelligence model (the **Chairman**) is called to act as the final editor.
*   **Full Context**: The Chairman pulls back the curtain. They see the **original creators** (A-GPT, B-Claude, C-Gemini), the individual peer reviews, and the final **Borda scores**.
*   **Executive Judgment**: The Chairman synthesizes the collective wisdom. It validates the majority view while "rescuing" unique, valid insights from lower-ranked models if they found a truth others missed.
*   **A Single Answer**: You receive one comprehensive, peer-verified response instead of three conflicting ones.

---

## Key Reliability Features

### 1. Self-Preference Protection
Models often prefer their own style. To stop this, the Council uses **Self-Voting Exclusion**. Any vote a model gives to its own response is automatically discarded by the scoring algorithm. A model only wins if its *competitors* acknowledge its quality.

### 2. Randomization
To prevent "Position Bias," the Council randomizes the order of the responses for every single model during the judging stage. This ensures a model doesn't win just because its answer appeared first on the list.

### 3. Reliability & Fallbacks
If a specific model (like a new preview model) fails or hits a rate limit, the Council doesn't crash. It uses **Graceful Degradation** to proceed with the remaining successful responses, ensuring you still get an answer even if one provider has a hiccup.

### 4. Direct Accountability
By using the `--details` flag (Terminal) or `include_details` (Claude), you can see exactly how each model voted and what they said in private before the final summary was written.

---

## When to Use the Council
*   **High-Stakes Decisions**: When you need a second (and third, and fourth) opinion before committing to a path.
*   **Complex Debugging**: When different AIs have different specialized "knowledge" about a library or language.
*   **Strategic Planning**: When you want to see a problem from multiple competitive perspectives (e.g., getting the "Anthropic view" and the "OpenAI view" simultaneously).
