# Multi-Model Deliberation: How LLM Council Verifies Code

*Published: January 2026*

---

Code review is hard. It requires understanding context, spotting subtle bugs, and making judgment calls about quality. What if multiple AI models could deliberate together, anonymously evaluate each other's reviews, and reach a consensus verdict?

That's exactly what LLM Council's verification system now does. This post explains how 3-stage deliberation produces more reliable code verification than any single model alone.

## The Problem with Single-Model Verification

When you ask one AI to verify code, you get one opinion. That opinion might be:

- **Biased** by the model's training data
- **Overconfident** despite uncertainty
- **Inconsistent** across similar inputs
- **Blind** to certain vulnerability classes

Enterprise teams can't ship code based on a single model's "looks good to me." They need structured evaluation with transparent reasoning.

## The 3-Stage Deliberation Architecture

LLM Council verification runs three distinct stages, each designed to address single-model limitations:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Stage 1   │ ──► │   Stage 2   │ ──► │   Stage 3   │
│   Review    │     │  Peer Rank  │     │  Synthesis  │
└─────────────┘     └─────────────┘     └─────────────┘
     │                    │                    │
     ▼                    ▼                    ▼
  Multiple           Anonymous            Chairman
  parallel           evaluation           renders
  reviews            of reviews           verdict
```

### Stage 1: Parallel Model Reviews

Each council model independently reviews the code snapshot:

```python
stage1_results, _ = await stage1_collect_responses(verification_query)
# Returns: [
#   {"model": "openai/gpt-4o", "response": "...detailed review..."},
#   {"model": "anthropic/claude-3.5-sonnet", "response": "..."},
#   {"model": "google/gemini-pro-1.5", "response": "..."},
# ]
```

Why multiple models? Each has different:
- Training data and knowledge cutoffs
- Reasoning patterns and blind spots
- Sensitivity to different vulnerability types

One model might catch SQL injection while missing XSS. Another might spot race conditions but overlook CSRF. Together, they cover more ground.

### Stage 2: Anonymous Peer Ranking

Here's where it gets interesting. Each model evaluates the other reviews *without knowing who wrote them*:

```python
stage2_results, label_to_model, _ = await stage2_collect_rankings(
    verification_query, stage1_results
)
# Reviews presented as "Response A", "Response B", "Response C"
# Models rank them AND score on rubric dimensions
```

The anonymization is crucial. Without it, models might:
- Defer to "more prestigious" model names
- Self-promote their own responses
- Form cliques based on provider relationships

With anonymization, evaluation is based solely on review quality.

**Rubric Dimensions**: Each reviewer scores responses on:
- **Accuracy**: Are findings correct?
- **Relevance**: Do they address the actual code?
- **Completeness**: Are all issues identified?
- **Conciseness**: Is the review actionable?
- **Clarity**: Is the reasoning understandable?

### Stage 3: Chairman Synthesis

The chairman model synthesizes all reviews and rankings into a final verdict:

```python
stage3_result, _, _ = await stage3_synthesize_final(
    verification_query,
    stage1_results,
    stage2_results,
    aggregate_rankings=aggregate_rankings,
    verdict_type=VerdictType.BINARY,
)
# Returns: {"model": "...", "response": "...\nFINAL_VERDICT: APPROVED\n..."}
```

The chairman sees:
- All original reviews (with model attribution)
- All peer rankings (showing consensus)
- Aggregate Borda scores (ranking-based voting where 1st place = N points, 2nd = N-1, etc.)

**Verdict Logic**: The chairman renders **APPROVED** or **REJECTED** (binary). The system then applies the confidence threshold:
- **PASS** (exit 0): APPROVED with confidence ≥ threshold (default 0.7)
- **FAIL** (exit 1): REJECTED
- **UNCLEAR** (exit 2): APPROVED but confidence below threshold, requires human review

## Dynamic Verdict Extraction

The raw synthesis needs structured extraction. That's where `verdict_extractor.py` comes in:

```python
def extract_verdict_from_synthesis(stage3_result, stage2_results, threshold=0.7):
    """Extract verdict and confidence from chairman synthesis."""
    response = stage3_result.get("response", "")

    # Calculate confidence from reviewer agreement
    confidence = calculate_confidence_from_agreement(stage2_results)

    # Look for structured verdict line (anchored for reliability)
    # Chairman is prompted to output: "FINAL_VERDICT: APPROVED" or "FINAL_VERDICT: REJECTED"
    verdict_match = re.search(r"^FINAL_VERDICT:\s*(APPROVED|REJECTED)", response, re.MULTILINE)

    if verdict_match:
        raw_verdict = verdict_match.group(1).upper()
        if raw_verdict == "APPROVED":
            # Apply confidence threshold for pass/unclear distinction
            if confidence >= threshold:
                return "pass", confidence
            return "unclear", confidence  # Low confidence triggers human review
        return "fail", confidence

    # No structured verdict found
    return "unclear", 0.50
```

**Confidence calculation** is based on council agreement:
- **Rubric score variance**: Low variance across reviewers = high confidence
- **Ranking agreement**: Reviewers ranking responses similarly = high confidence
- **Borda count spread**: Clear winner (large point gap) = high confidence

## Audit Trail: Complete Transparency

Every verification writes a complete transcript:

```
.council/logs/2026-01-01T12-00-00-abc123/
├── request.json    # What was asked
├── stage1.json     # All individual reviews
├── stage2.json     # All peer rankings + rubric scores
├── stage3.json     # Chairman synthesis
└── result.json     # Final verdict + confidence
```

This enables:
- **Debugging**: Why did verification fail?
- **Auditing**: Who said what?
- **Learning**: How do models disagree?
- **Compliance**: Reproducible decisions

## Exit Codes for CI/CD

Verification returns machine-readable exit codes:

| Verdict | Exit Code | CI Action |
|---------|-----------|-----------|
| PASS | 0 | Continue pipeline |
| FAIL | 1 | Block deployment |
| UNCLEAR | 2 | Request human review |

Integration is straightforward:

```yaml
# GitHub Actions example
- name: Verify code changes
  env:
    PR_NUMBER: ${{ github.event.pull_request.number }}
  run: |
    # Capture exit code without failing immediately
    set +e
    llm-council verify ${{ github.sha }}
    exit_code=$?
    set -e

    case $exit_code in
      0) echo "Verification passed" ;;
      1) echo "Verification failed - blocking deployment"; exit 1 ;;
      2) gh pr comment "$PR_NUMBER" --body "Verification unclear - requesting human review"
         echo "Flagged for human review"; exit 0 ;;
    esac
```

## What Makes This Different

Other AI verification approaches typically:
1. Use a single model (single point of failure)
2. Skip peer review (no quality check on reviews)
3. Return unstructured output (hard to automate)
4. Leave no audit trail (impossible to debug)

LLM Council verification provides:
- **Multi-model consensus** reducing individual bias
- **Anonymous peer review** ensuring quality evaluation
- **Structured verdicts** enabling automation
- **Complete transcripts** enabling transparency

## Try It

The verification system is available via MCP:

```python
# Via MCP client
result = await mcp_client.call_tool(
    "mcp://llm-council/verify",
    {
        "snapshot_id": "abc1234",
        "target_paths": ["src/"],
        "rubric_focus": "Security",
        "confidence_threshold": 0.7
    }
)
print(f"Verdict: {result.verdict} (confidence: {result.confidence})")
```

Or via the skills-based approach in Claude Code:

```bash
# In Claude Code
/council-verify --snapshot HEAD~1 --focus security
```

---

*Multi-model deliberation isn't just about having multiple opinions—it's about structured evaluation, transparent reasoning, and reproducible decisions. That's what enterprise code verification requires.*
