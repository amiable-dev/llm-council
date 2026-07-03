# Eval-Framework Bridges (ADR-048 P3)

Drive the council as an evaluation TARGET from external eval suites, via the
dependency-free adapters in `llm_council.bench.adapters`:

- `make_council_eval_callable()` — async `prompt -> answer` callable
  (DeepEval-style harnesses); accepts sync or async injected runners.
- `council_to_ragas_row(question, result)` — RAGAS dataset row: chairman
  synthesis as `answer`, successful stage-1 drafts as `contexts`.

## Prerequisites

- A configured council (`OPENROUTER_API_KEY` or keychain via
  `llm-council setup-key`)
- The framework you're bridging to (NOT project dependencies):
  `pip install deepeval` or `pip install ragas datasets`

## Cost warning

**Every evaluated prompt runs a full council deliberation — real API
spend.** Apply your eval framework's own budgets/limits; there is no cap
inside these adapters (unlike `llm-council bench`, which caps runs).

## Round-trips

```bash
python examples/eval_bridges/deepeval_example.py
python examples/eval_bridges/ragas_example.py
```
