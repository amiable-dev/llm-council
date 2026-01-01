# Council Verification Integration Announcements

Social media content for the full council deliberation integration in ADR-034 verification.

---

## Twitter/X Threads

### Thread 1: Feature Announcement (SM3)

**Tweet 1 (Main):**
```
LLM Council verification now runs real 3-stage deliberation.

Not mocked. Not placeholder values. Actual multi-model consensus on your code.

Stage 1: Parallel reviews
Stage 2: Anonymous peer ranking
Stage 3: Chairman verdict

Full audit trail for every decision.
```

**Tweet 2:**
```
What does "real deliberation" mean?

Before: API returned hardcoded confidence scores
After: Scores extracted from actual model agreement

High rubric agreement = high confidence
Clear Borda winner = high confidence
Models disagreeing = low confidence → human review
```

**Tweet 3:**
```
Every verification now writes:

.council/logs/{id}/
├── request.json
├── stage1.json  ← All model reviews
├── stage2.json  ← Peer rankings + rubrics
├── stage3.json  ← Chairman synthesis
└── result.json

Complete transparency. Debug any verdict.
```

**Tweet 4:**
```
CI/CD integration with exit codes:

0 = PASS → deploy
1 = FAIL → block
2 = UNCLEAR → human review

The UNCLEAR verdict is key. Low confidence doesn't force a decision—it asks for help.

pip install llm-council-core
```

---

### Thread 2: Technical Deep Dive (SM4)

**Tweet 1:**
```
How we extract verdicts from multi-model consensus:

The chairman writes "FINAL_VERDICT: APPROVED"
We parse with anchored regex (not keyword matching)
Then apply confidence threshold

APPROVED + high confidence = PASS
APPROVED + low confidence = UNCLEAR
REJECTED = FAIL
```

**Tweet 2:**
```
Confidence calculation:

1. Rubric score variance across reviewers
   Low variance = high agreement = high confidence

2. Borda count spread
   Clear winner = decisive consensus = high confidence

3. Ranking correlation
   Models ranking similarly = aligned evaluation
```

**Tweet 3:**
```
Why anonymized peer review matters:

Stage 2 presents "Response A, B, C"—not model names.

Prevents:
• GPT favoring GPT responses
• Claude deferring to Claude
• Clique formation

Evaluation based on quality, not reputation.
```

**Tweet 4:**
```
The accuracy ceiling (from ADR-016):

A well-written lie is dangerous.

If accuracy < 5: max score = 4.0
If accuracy < 7: max score = 7.0

No eloquence bonus for incorrect code reviews.
```

**Tweet 5:**
```
Try it:

llm-council verify abc1234 --focus security

Or via MCP:
mcp://llm-council/verify

Returns structured verdict with confidence score and audit trail location.

GitHub: github.com/amiable-dev/llm-council
```

---

## Hacker News

### Show HN Post

**Title:**
```
Show HN: Full multi-model deliberation for code verification (not mocked)
```

**Text:**
```
Hey HN,

We just shipped real council deliberation for our verification API. Previously it returned placeholder values; now every verification runs actual 3-stage multi-model consensus.

The difference matters:

Before:
- Always returned 0.85 confidence
- No actual model evaluation
- Tests passed by mocking the core function

After:
- Confidence calculated from reviewer agreement
- All three stages (review, peer-rank, synthesize) executed
- Full transcript written: stage1.json, stage2.json, stage3.json

How it works:

1. Stage 1: 4+ models independently review your code snapshot
2. Stage 2: Each model anonymously ranks all reviews (sees "Response A" not "GPT-4")
3. Stage 3: Chairman synthesizes verdict from rankings

The exit codes enable CI/CD integration:
- 0 = PASS → proceed
- 1 = FAIL → block
- 2 = UNCLEAR → human review required

That UNCLEAR state is crucial. When models disagree, the system expresses uncertainty rather than forcing a decision.

Technical notes:
- Verdict extraction uses anchored regex (^FINAL_VERDICT:)
- Confidence derived from Borda score spread and rubric variance
- Accuracy ceiling caps eloquent-but-wrong responses

We caught the "placeholder values" gap through our own dogfooding. Council-reviewed the implementation, found the issue, created a gap analysis, then fixed it with TDD.

GitHub: https://github.com/amiable-dev/llm-council
Blog post explaining the architecture: [link to blog]

Would love feedback on the confidence calculation approach.
```

---

## Reddit

### r/LocalLLaMA Post

**Title:**
```
LLM Council now runs real multi-model deliberation for code verification
```

**Body:**
```
Just shipped a significant update to LLM Council verification.

**What changed?**

The verification API was returning placeholder values (always 0.85 confidence, always "pass"). We caught this through dogfooding and fixed it properly with TDD.

Now every verification runs actual 3-stage deliberation:

1. **Stage 1**: Multiple models independently review your code
2. **Stage 2**: Anonymous peer ranking (models see "Response A" not "Claude")
3. **Stage 3**: Chairman synthesizes a verdict

**Why this matters**

The confidence score is now meaningful:
- High agreement among reviewers = high confidence
- Clear Borda winner = high confidence
- Models disagreeing = low confidence → triggers UNCLEAR verdict

**Audit trail**

Every verification writes:
```
.council/logs/{id}/
├── stage1.json  # All reviews
├── stage2.json  # Peer rankings
├── stage3.json  # Chairman synthesis
└── result.json  # Final verdict
```

You can debug any decision.

**CI/CD integration**

Exit codes:
- 0 = PASS
- 1 = FAIL
- 2 = UNCLEAR (human review needed)

```bash
llm-council verify abc1234 --focus security
```

GitHub: https://github.com/amiable-dev/llm-council

The gap analysis document is in the repo if you want to see how we caught and fixed this.
```

---

## LinkedIn Post

```
Shipped real multi-model deliberation for code verification.

Previously, our verification API returned placeholder values. We caught this through dogfooding—running the council to verify its own implementation.

Now every verification runs actual 3-stage deliberation:

Stage 1: Multiple models independently review code
Stage 2: Anonymous peer ranking (prevents model favoritism)
Stage 3: Chairman synthesizes verdict from consensus

The confidence score is now meaningful:
• Calculated from reviewer agreement
• Based on Borda score spread
• Triggers UNCLEAR verdict when models disagree

CI/CD exit codes:
✅ 0 = PASS
❌ 1 = FAIL
⚠️ 2 = UNCLEAR (request human review)

Full audit trail: every decision writes stage1.json, stage2.json, stage3.json for debugging and compliance.

The irony isn't lost on me—we used multi-model consensus to catch that multi-model consensus wasn't actually running. Dogfooding works.

Open source: github.com/amiable-dev/llm-council

#AIEngineering #CodeReview #LLMOps #OpenSource
```

---

## Discord / Slack Communities

### Short Announcement

```
🔧 **LLM Council Verification: Now with Real Deliberation**

The verification API now runs actual 3-stage multi-model consensus.

What's new:
• Dynamic confidence from reviewer agreement
• Full transcript (stage1/2/3.json)
• UNCLEAR verdict when models disagree

Exit codes for CI/CD: 0=PASS, 1=FAIL, 2=UNCLEAR

pip install llm-council-core
llm-council verify abc1234 --focus security

GitHub: github.com/amiable-dev/llm-council
```

---

## Posting Schedule Suggestion

| Platform | Best Time (UTC) | Day |
|----------|-----------------|-----|
| Twitter/X | 14:00-16:00 | Tuesday-Thursday |
| Hacker News | 14:00-15:00 | Tuesday-Wednesday |
| Reddit r/LocalLLaMA | 15:00-17:00 | Any weekday |
| LinkedIn | 13:00-15:00 | Tuesday-Thursday |
| Discord/Slack | Any | Any |

---

## Hashtags Reference

**Twitter/X:**
```
#LLMCouncil #AIEngineering #MultiModel #CodeVerification #DevOps #OpenSource
```

**LinkedIn:**
```
#AIEngineering #CodeReview #LLMOps #OpenSource #DevTools #MachineLearning
```
