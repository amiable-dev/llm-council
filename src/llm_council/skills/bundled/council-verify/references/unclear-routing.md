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

**Structured findings (ADR-051).** The `low_confidence` "accept when
`blocking_issues` is empty" policy above assumes `blocking_issues` reflects the
verdict. Under `LLM_COUNCIL_STRUCTURED_FINDINGS=true` it always does (the
verdict is computed as `fail` iff any `critical` finding exists), and you can
route on the richer `findings`/`severity` instead. With the flag **off**
(default), `blocking_issues` is prose-scraped and may be empty even on a real
FAIL — so prefer keying on `verdict` and `findings`, not `blocking_issues == []`.

## Calibrated confidence (ADR-047 P2)

`confidence_calibrated` is the raw confidence passed through the persisted
monotonic calibration mapping (`.council/calibration/mapping.json`). It equals
the raw value until a mapping is fitted from human dispositions:

```bash
llm-council calibration-report --fit
```

The PASS threshold consumes the calibrated value only behind
`LLM_COUNCIL_CALIBRATED_CONFIDENCE=true` (default off).
