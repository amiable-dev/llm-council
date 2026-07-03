"""DeepEval round-trip example (ADR-048 P3): the council as an eval target.

Requires: pip install deepeval  (not a project dependency)
Costs REAL API spend per test case.
"""

import asyncio

from llm_council.bench.adapters import make_council_eval_callable


def main() -> None:
    try:
        from deepeval.metrics import AnswerRelevancyMetric
        from deepeval.test_case import LLMTestCase
    except ImportError:
        raise SystemExit("pip install deepeval to run this example")

    generate = make_council_eval_callable()
    question = "In one paragraph, what is the CAP theorem?"
    answer = asyncio.run(generate(question))

    case = LLMTestCase(input=question, actual_output=answer)
    metric = AnswerRelevancyMetric(threshold=0.7)
    metric.measure(case)
    print(f"council answer scored {metric.score} (threshold 0.7)")


if __name__ == "__main__":
    main()
