# UNCLEAR Routing (ADR-047)

On an `unclear` verdict, `unclear_reason` says why. The exit code stays `2`
for all three causes — that is the ADR-047 compatibility contract; the REASON
field, not the exit code, is the routing signal ("accept-and-audit" etc. are
caller policies applied on top of exit 2, never different exit codes):

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
