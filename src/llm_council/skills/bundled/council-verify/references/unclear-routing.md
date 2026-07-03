# UNCLEAR Routing (ADR-047)

On an `unclear` verdict (exit code 2), `unclear_reason` says why. Route on it
instead of treating every UNCLEAR alike:

| unclear_reason | Meaning | Action |
|---|---|---|
| `infra_failure` | the chairman call itself errored (billing 402, auth, rate-limit, transport) | check gateway/billing, RETRY — never treat as a review outcome |
| `low_confidence` | deliberation completed, confidence below threshold | accept-and-audit per policy when `blocking_issues` is empty |
| `timeout` | the tier deadline fired (`timeout_fired: true`) | re-tier (e.g. balanced) or reduce input scope |

`unclear_reason` is `null` for pass/fail and on non-deliberated cap results
(where the `error` marker governs, e.g. `input_too_large`).

## Calibrated confidence (ADR-047 P2)

`confidence_calibrated` is the raw confidence passed through the persisted
monotonic calibration mapping (`.council/calibration/mapping.json`). It equals
the raw value until a mapping is fitted from human dispositions:

```bash
llm-council calibration-report --fit
```

The PASS threshold consumes the calibrated value only behind
`LLM_COUNCIL_CALIBRATED_CONFIDENCE=true` (default off).
