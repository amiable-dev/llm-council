"""Thin eval-framework bridges (ADR-048 P3 / ADR-036 P3 commitment, #420).

External eval suites drive the council as a TARGET through two adapters —
deliberately dependency-free (no deepeval/ragas imports here; the examples
under ``examples/eval_bridges/`` show framework-side wiring):

- ``make_council_eval_callable`` — an async ``prompt -> answer`` callable,
  the shape DeepEval-style harnesses use to generate ``actual_output``.
- ``council_to_ragas_row`` — maps one deliberation onto the RAGAS dataset
  row shape: the chairman synthesis is the ``answer`` and the stage-1
  drafts serve as ``contexts`` (the material the synthesis drew from).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional


def make_council_eval_callable(
    council_runner: Optional[Callable[..., Any]] = None,
) -> Callable[[str], Any]:
    """An async ``prompt -> synthesis text`` callable for eval harnesses.

    ``council_runner`` is injectable for tests; the default runs the real
    council — REAL SPEND, so eval suites should apply their own budgets.
    """
    if council_runner is None:  # pragma: no cover - real spend path

        async def council_runner(prompt: str) -> Dict[str, Any]:
            from llm_council.council import run_council_with_fallback

            return await run_council_with_fallback(prompt, bypass_cache=True)

    async def generate(prompt: str) -> str:
        result = await council_runner(prompt)
        return result.get("synthesis", "")

    return generate


def council_to_ragas_row(question: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Map a council result onto the RAGAS row shape.

    ``contexts`` carries the successful stage-1 drafts — the retrieved
    material the chairman synthesized from; failed models are excluded.
    """
    contexts = []
    for status in (result.get("model_responses") or {}).values():
        if isinstance(status, dict) and status.get("status") == "ok":
            response = status.get("response")
            if response:
                contexts.append(response)
    return {
        "question": question,
        "answer": result.get("synthesis", ""),
        "contexts": contexts,
    }
