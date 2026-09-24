# The performance store

LLM Council keeps a local record of how each model performed, one JSON object
per line, at:

```
~/.llm-council/performance_metrics.jsonl
```

Set `LLM_COUNCIL_PERFORMANCE_STORE` to move it, or
`LLM_COUNCIL_PERFORMANCE_TRACKING=false` to switch recording off entirely.

Each record carries the model, the session it belonged to, latency, its Borda
score from peer review, whether its ranking parsed, and — when the provider
reported one — the cost in USD.

## Reading a cost total

```bash
jq -s 'map(select(.cost_usd != null) | .cost_usd) | add' \
  ~/.llm-council/performance_metrics.jsonl
```

Two things to understand before comparing that number with a provider invoice.

**`cost_usd: null` is not zero.** A null means no cost was observed for that
call; a `0` means the call really was free — a cached response, a free tier, a
local model. Summing them together would be wrong in a way that is invisible,
so the filter above drops nulls rather than coercing them. If you want to know
how much of the file is accounted for:

```bash
jq -s 'group_by(.cost_usd == null) | map({null_cost: .[0].cost_usd == null, n: length})' \
  ~/.llm-council/performance_metrics.jsonl
```

**Check which paths were recording.** Before v0.50.0 only the verify path wrote
records; `consult` runs — usually the larger share of spend — wrote nothing at
all. A total from a file spanning that change will under-count, and the missing
amount is not recoverable from the file.

## Removing test fixture rows

Council test suites before v0.50.0 wrote fixture records into the real store
instead of a temporary one (issue #693). They are recognisable by a `test/`
model id — most commonly `test/model-a` — and they carry a null cost, which
makes an otherwise complete file look as though a third of its cost capture had
failed.

Count them:

```bash
grep -c '"model_id": *"test/' ~/.llm-council/performance_metrics.jsonl
```

Remove them, keeping a backup:

```bash
cp ~/.llm-council/performance_metrics.jsonl ~/.llm-council/performance_metrics.jsonl.bak
grep -v '"model_id": *"test/' ~/.llm-council/performance_metrics.jsonl.bak \
  > ~/.llm-council/performance_metrics.jsonl
```

Or with `jq`, if you prefer to parse rather than match text:

```bash
jq -c 'select(.model_id | startswith("test/") | not)' \
  ~/.llm-council/performance_metrics.jsonl.bak \
  > ~/.llm-council/performance_metrics.jsonl
```

**Council never rewrites this file for you.** There is no migration on upgrade
and there will not be one. It is your data, it is the only copy, and a tool
that silently edits a measurement record is a tool whose totals you can no
longer trust. The commands above are yours to run when you choose.

Any model id you genuinely use that begins with `test/` would be caught by
these filters too — check the count first if that is a possibility.

## Why records exist at all

The store backs the internal performance index (ADR-026 Phase 3): the
confidence tiers for a model's measured behaviour, the cost-per-quality
ranking, and the latency figures that decide whether a model fits a tier's
time budget. It is local by default and never leaves the machine unless you
configure an exporter.
