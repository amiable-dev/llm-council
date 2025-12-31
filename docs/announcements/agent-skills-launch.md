# Agent Skills Launch Announcements

Prepared social media content for the ADR-034 Agent Skills release.

---

## Twitter/X Threads

### Thread 1: Feature Announcement

**Tweet 1 (Main):**
```
LLM Council now supports Agent Skills for AI code assistants.

Use multi-model consensus to:
• Verify implementation correctness
• Review PRs with security focus
• Gate CI/CD deployments

Works with Claude Code, VS Code Copilot, Cursor, and more.

https://llm-council.dev/guides/skills/
```

**Tweet 2:**
```
Why multi-model verification?

A single AI can confidently generate buggy code AND confidently say it's correct.

Multiple models with different training = different blind spots.

Consensus catches what individuals miss.
```

**Tweet 3:**
```
Three skills included:

council-verify → General work verification
council-review → Code review (35% accuracy weight)
council-gate → CI/CD with exit codes (0=PASS, 1=FAIL, 2=UNCLEAR)

The UNCLEAR verdict is key: "humans should review this"
```

**Tweet 4:**
```
Defense-in-depth security:

• Context isolation (no conversation bleed)
• Snapshot pinning (verify specific commits)
• XML sandboxing (prompt injection defense)
• Anonymized peer review (no model favoritism)
• Multi-provider diversity (min 2 providers)

Full architecture: https://llm-council.dev/blog/11-verification-security-architecture/
```

**Tweet 5:**
```
Get started:

pip install llm-council-core
export OPENROUTER_API_KEY=sk-or-...

# In your AI assistant
/council-verify --snapshot HEAD --file-paths "src/feature.py"

Docs: https://llm-council.dev/guides/skills/
GitHub: https://github.com/amiable-dev/llm-council
```

---

### Thread 2: Technical Deep Dive

**Tweet 1:**
```
How do you prevent an AI assistant from verifying its own work incorrectly?

Answer: Don't let it verify alone.

We built Agent Skills on top of LLM Council's 3-stage deliberation.

Here's the security architecture 🧵
```

**Tweet 2:**
```
Layer 1: Context Isolation

Every verification runs in a fresh context.

No conversation history. No previous verdicts. Just the snapshot and query.

A compromised assistant can't pollute the verification with primed beliefs.
```

**Tweet 3:**
```
Layer 2: Snapshot Pinning

Verification targets a specific git commit, not "current state."

Prevents TOCTOU attacks: can't change files between verification and deployment.

The SHA appears in the audit trail.
```

**Tweet 4:**
```
Layer 3: Anonymized Peer Review

During Stage 2, models see "Response A, B, C" not "GPT-4, Claude, Gemini."

Prevents:
• Model favoritism (GPT preferring GPT)
• Reputation attacks
• Coordination attempts
```

**Tweet 5:**
```
Layer 4: Accuracy Ceiling

A well-written lie is more dangerous than a poorly-written truth.

We cap scores based on accuracy:
• Accuracy < 5 → max score 4.0
• Accuracy < 7 → max score 7.0

No eloquence bonus for incorrect answers.
```

**Tweet 6:**
```
Full 8-layer architecture:
1. Context isolation
2. Snapshot pinning
3. XML sandboxing
4. Anonymized review
5. Multi-provider diversity
6. Accuracy ceiling
7. Audit trails
8. Exit codes

Blog: https://llm-council.dev/blog/11-verification-security-architecture/
```

---

## Hacker News

### Show HN Post

**Title:**
```
Show HN: Agent Skills – Multi-model consensus for AI code verification
```

**Text:**
```
Hey HN,

I built Agent Skills for LLM Council, a system that lets AI code assistants verify their own work using multi-model consensus.

The problem: AI assistants confidently generate code, then confidently claim it's correct. Self-review doesn't catch blind spots because the same reasoning that produced the bug will miss it.

The solution: Multiple models with different training evaluate the same work. Consensus catches what individuals miss.

Three skills included:
- council-verify: General work verification
- council-review: Code review with 35% accuracy weight
- council-gate: CI/CD quality gates with exit codes (0=PASS, 1=FAIL, 2=UNCLEAR)

The UNCLEAR verdict (exit code 2) is key—it means "the council couldn't reach confident consensus, humans should review."

Security architecture includes:
- Context isolation (no conversation bleed)
- Snapshot pinning (verify specific commits)
- Anonymized peer review (models see "Response A" not "GPT-4")
- Multi-provider diversity (requires 2+ providers)
- Accuracy ceiling (eloquent wrong answers get capped)

Works with Claude Code, VS Code Copilot, Cursor, and other MCP-compatible clients.

GitHub: https://github.com/amiable-dev/llm-council
Docs: https://llm-council.dev/guides/skills/
Security architecture: https://llm-council.dev/blog/11-verification-security-architecture/

Would love feedback on the approach. The audit trail feature was heavily requested—every verification produces a complete transcript for debugging and compliance.
```

---

## Reddit

### r/LocalLLaMA Post

**Title:**
```
Agent Skills: Use multi-model consensus to verify AI-generated code
```

**Body:**
```
Just released Agent Skills for LLM Council—a way to have multiple LLMs verify code that your AI assistant generates.

**The Problem**

When Claude/GPT/etc writes code, it can confidently generate bugs and then confidently say the code is correct. Self-review doesn't work because the same reasoning that produced the bug misses it on review.

**The Solution**

Multiple models with different training evaluate the same work. They anonymously peer-review each other (models see "Response A" not "Claude"), then we synthesize a verdict.

Three skills:
- `council-verify` - General verification
- `council-review` - Code review (security, performance, testing focus)
- `council-gate` - CI/CD gates with exit codes (0=PASS, 1=FAIL, 2=UNCLEAR)

**What I like about this**

The UNCLEAR verdict is the key innovation. Instead of forcing binary pass/fail, exit code 2 means "the council couldn't reach confident consensus—a human should review."

**Security**

- Context isolation: Each verification is fresh, no conversation pollution
- Anonymized review: Prevents model favoritism
- Multi-provider diversity: Requires 2+ different providers (OpenAI + Anthropic, etc.)
- Accuracy ceiling: Eloquent wrong answers get score-capped

**Try it**

```bash
pip install llm-council-core
export OPENROUTER_API_KEY=sk-or-...
```

Works with Claude Code, Copilot, Cursor, etc.

GitHub: https://github.com/amiable-dev/llm-council
Docs: https://llm-council.dev/guides/skills/

Happy to answer questions about the architecture.
```

---

### r/MachineLearning Post

**Title:**
```
[P] Multi-model consensus for AI code verification: Agent Skills for LLM Council
```

**Body:**
```
Released Agent Skills, a system for AI code assistants to verify their work using multi-model deliberation.

**Motivation**

Single-model self-verification has a fundamental limitation: the same biases that produce errors also miss them during review. Multi-model consensus with diverse providers (different training data, different RLHF) provides orthogonal perspectives.

**Architecture**

Three-stage deliberation:
1. **Stage 1**: N models independently answer the verification query
2. **Stage 2**: Each model anonymously evaluates all responses (sees "Response A, B, C" not model IDs)
3. **Stage 3**: Chairman model synthesizes a verdict from responses + peer reviews

**Bias Mitigation**

- Response order randomization (prevents position bias)
- Anonymized peer review (prevents model favoritism)
- Multi-provider diversity constraint (minimum 2 providers required)
- Accuracy ceiling: weighted score is capped by accuracy dimension
  - Accuracy < 5 → max 4.0 (prevents eloquent lies from ranking well)
  - Accuracy < 7 → max 7.0

**CI/CD Integration**

Exit codes enable pipeline integration:
- 0: PASS (proceed with deployment)
- 1: FAIL (block deployment)
- 2: UNCLEAR (require human review)

The UNCLEAR state addresses the confidence calibration problem—rather than forcing a binary decision, the system can express uncertainty.

**Evaluation**

Using ADR-016 multi-dimensional rubric scoring: accuracy (30%), completeness (25%), clarity (20%), conciseness (15%), relevance (10%). Code review skill increases accuracy to 35%.

GitHub: https://github.com/amiable-dev/llm-council
Technical blog: https://llm-council.dev/blog/11-verification-security-architecture/

Interested in feedback on the bias mitigation approach, particularly whether the anonymization + diversity constraints are sufficient or if additional techniques would help.
```

---

## LinkedIn Post

```
Excited to announce Agent Skills for LLM Council!

AI code assistants are powerful, but they can't reliably verify their own work. The same reasoning that produces a bug will miss it during self-review.

Our solution: multi-model consensus.

Multiple AI models with different training evaluate the same code changes. They anonymously peer-review each other, then synthesize a verdict. Different models = different blind spots = better coverage.

Three skills included:
• council-verify: General work verification
• council-review: Code review with security focus
• council-gate: CI/CD quality gates

The CI/CD integration supports three outcomes:
✅ PASS (exit code 0) - proceed with deployment
❌ FAIL (exit code 1) - block deployment
⚠️ UNCLEAR (exit code 2) - require human review

That UNCLEAR state is crucial. Instead of forcing a binary decision, the system can express "I'm not confident enough—a human should look at this."

Defense-in-depth security includes context isolation, snapshot pinning, anonymized peer review, and multi-provider diversity requirements.

Works with Claude Code, VS Code Copilot, Cursor, and other AI coding tools.

Open source: https://github.com/amiable-dev/llm-council
Documentation: https://llm-council.dev/guides/skills/

#AIEngineering #DevTools #CodeReview #OpenSource
```

---

## Discord / Slack Communities

### Short Announcement

```
🎉 **Agent Skills for LLM Council**

Multi-model consensus for AI code verification is here!

Have your AI assistant verify its own work using multiple models:
- `council-verify` - General verification
- `council-review` - Code review
- `council-gate` - CI/CD gates (exit codes 0/1/2)

Works with Claude Code, Copilot, Cursor.

Docs: https://llm-council.dev/guides/skills/
GitHub: https://github.com/amiable-dev/llm-council
```

---

## Posting Schedule Suggestion

| Platform | Best Time (UTC) | Day |
|----------|-----------------|-----|
| Twitter/X | 14:00-16:00 | Tuesday-Thursday |
| Hacker News | 14:00-15:00 | Tuesday-Wednesday |
| Reddit r/LocalLLaMA | 15:00-17:00 | Any weekday |
| Reddit r/MachineLearning | 14:00-16:00 | Monday-Wednesday |
| LinkedIn | 13:00-15:00 | Tuesday-Thursday |
| Discord/Slack | Any | Any |

---

## Hashtags Reference

**Twitter/X:**
```
#LLMCouncil #AIEngineering #MultiModel #CodeReview #DevTools #OpenSource #AIAssistant #ClaudeCode #Copilot
```

**LinkedIn:**
```
#AIEngineering #DevTools #CodeReview #OpenSource #MachineLearning #SoftwareEngineering #AI #LLM
```
