"""RAGAS round-trip example (ADR-048 P3): council deliberations as a dataset.

Requires: pip install ragas datasets  (not project dependencies)
Costs REAL API spend per question.
"""

import asyncio

from llm_council.bench.adapters import council_to_ragas_row


async def build_rows(questions):
    from llm_council.council import run_council_with_fallback

    rows = []
    for q in questions:
        result = await run_council_with_fallback(q, bypass_cache=True)
        rows.append(council_to_ragas_row(q, result))
    return rows


def main() -> None:
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, faithfulness
    except ImportError:
        raise SystemExit("pip install ragas datasets to run this example")

    rows = asyncio.run(build_rows(["What is the CAP theorem?"]))
    dataset = Dataset.from_list(rows)
    print(evaluate(dataset, metrics=[faithfulness, answer_relevancy]))


if __name__ == "__main__":
    main()
