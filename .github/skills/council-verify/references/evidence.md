# Pre-computed Evidence (ADR-042)

Pass pre-computed analysis output from upstream tools (linters, slop detectors, custom checkers) as an `evidence` parameter on the `verify` MCP tool. The council renders evidence inside structured prompt sections and emits per-source dispositions in the response.

## EvidenceItem fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `evidence_id` | string \| null | null | Stable id for disambiguating duplicate `source` values. `^[A-Za-z0-9._\-]{1,64}$`. Auto-assigned as `auto-N` if omitted. |
| `source` | string | required | Tool name + version (e.g. `ai-slop-detector@3.7.3`). `^[A-Za-z0-9._@/\-+]{1,200}$`. |
| `format` | `"markdown"\|"json"\|"text"` | `"markdown"` | Hint to the model. All formats are wrapped in `<evidence_item>` tags with tilde-fenced bodies. |
| `content` | string | required | Body. Max 50 000 chars per item; max 250 000 chars total per request. |
| `strength` | `"informational"\|"blocking"` | `"informational"` | `blocking` asks the council to verify the finding. Council retains final say — it is **not** a force-FAIL. |

## Limits

- Up to **20 items** per request.
- Per-tier budget (carved from the tier prompt cap **before** file content): `quick=1.5K chars`, `balanced=6K`, `high/reasoning=10K`.
- Items are dropped whole when the budget is exceeded; **a single blocking item that itself exceeds the budget causes a structured 422 error** (the API refuses to silently drop a blocking finding).

## Example

```json
{
  "snapshot_id": "abc1234",
  "target_paths": ["src/feature.py"],
  "tier": "balanced",
  "evidence": [
    {
      "source": "ai-slop-detector@3.7.3",
      "format": "markdown",
      "content": "Detected 3 phantom-stub functions in src/feature.py:42,57,89.",
      "strength": "informational"
    },
    {
      "source": "antislop@0.3.0",
      "format": "json",
      "content": "{\"violations\": [{\"file\": \"src/feature.py\", \"line\": 42, \"rule\": \"any-type-leak\"}]}",
      "strength": "blocking"
    }
  ]
}
```

## Response additions

- `evidence_summary`: `List[EvidenceDisposition]` — one entry per submitted item with `status ∈ {acknowledged, confirmed, rejected, unresolved, not_reviewed_due_to_budget, parser_error}`.
- `evidence_warnings`: `List[EvidenceWarning]` — structured budgeting/handling notes.
- `input_metrics.evidence_*`: per-strength counters and budget usage.

## Caller responsibility — out-of-scope file leak

Evidence content may quote lines from files outside `target_paths` (e.g., a scanner that walked the whole repo). Council will reason over whatever appears in the body. **The verify API does not police evidence content against `target_paths`.** If you need strict scope, pre-filter evidence to lines in your `target_paths` before submission.

## Adversarial content

Evidence bodies are treated as DATA, not as instructions, via structural XML-sentinel wrappers and an explicit instruction clause. Prompt-injection text like `"Ignore previous instructions"` inside an evidence body does not flip the verdict. The council is asked to flag suspicious imperatives in synthesis.
