"""Quality-per-dollar configuration matrix (ADR-048 P2, #419).

Runs the same golden dataset across configurations — each council member
solo, the full council, and (flag-on) ADR-044 graduated depth — and renders
the empirical answer to "when does deliberation pay?" using ADR-011 actual
costs. Methodology and caveats: ``bench/METHODOLOGY.md``.

Scoring note: solo configurations produce no council consensus, so envelope
``min_score`` floors are skipped for ``kind="solo"`` (documented in the
methodology); key-content assertions apply to every configuration equally.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .harness import run_bench

logger = logging.getLogger(__name__)


@dataclass
class MatrixConfig:
    """One column of the matrix."""

    name: str
    kind: str  # "solo" | "council" | "graduated"
    runner: Optional[Callable[..., Any]] = None  # injectable; real by default


def quality_per_dollar(
    *, pass_rate: float, cost_usd: float, cost_known: bool
) -> Optional[float]:
    """Pass-rate per dollar of KNOWN spend; None when it cannot be honest.

    Unknown or zero cost yields None rather than a fabricated/infinite
    figure — ADR-011: never present an estimate as a bill.
    """
    if not cost_known or cost_usd <= 0:
        return None
    return round(pass_rate / cost_usd, 3)


def _default_runner(config: MatrixConfig) -> Callable[..., Any]:
    """Build the real runner for a config — REAL SPEND.

    Unknown kinds raise (#440 r2): a typo must never silently fall through
    to the full-council runner and spend money on the wrong configuration.

    Concurrency note: run_matrix executes configs strictly SEQUENTIALLY, so
    the per-call env swap in the graduated runner has no concurrent reader;
    running matrix configs concurrently would require threading the ADR-044
    flag as a parameter instead.
    """
    if config.kind not in ("solo", "council", "graduated"):
        raise ValueError(f"unknown matrix kind: {config.kind!r}")
    if config.kind == "solo":
        model = config.name.split(":", 1)[1]

        async def solo_runner(prompt: str) -> Dict[str, Any]:
            from llm_council.gateway_adapter import query_model_with_status

            response = await query_model_with_status(
                model, [{"role": "user", "content": prompt}], timeout=120.0
            )
            usage = (response or {}).get("usage") or {}
            return {
                "synthesis": (response or {}).get("content") or "",
                "metadata": {
                    "aggregate_rankings": [],
                    "usage": {
                        "total": {
                            "cost_usd": usage.get("cost") or 0.0,
                            "cost_known": usage.get("cost") is not None,
                        }
                    },
                },
            }

        return solo_runner

    async def council_runner(prompt: str) -> Dict[str, Any]:
        import os

        import llm_council.council as council_mod

        if config.kind != "graduated":
            return await council_mod.run_council_with_fallback(prompt, bypass_cache=True)
        # Set the ADR-044 flag for THIS call only and always restore it —
        # leaking it would silently turn every later matrix config into a
        # graduated run, invalidating the comparison (#440 review).
        previous = os.environ.get("LLM_COUNCIL_GRADUATED_DEPTH")
        os.environ["LLM_COUNCIL_GRADUATED_DEPTH"] = "true"
        try:
            return await council_mod.run_council_with_fallback(prompt, bypass_cache=True)
        finally:
            if previous is None:
                os.environ.pop("LLM_COUNCIL_GRADUATED_DEPTH", None)
            else:
                os.environ["LLM_COUNCIL_GRADUATED_DEPTH"] = previous

    return council_runner


async def run_matrix(
    configs: List[MatrixConfig],
    *,
    dataset_dir: Optional[Path] = None,
    runs_dir: Optional[Path] = None,
    max_usd: Optional[float] = None,
    items_filter: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Run every configuration against a SHARED matrix-wide budget (#511).

    ``max_usd`` is the TOTAL ceiling across every config, not a per-config
    cap: passing the same cap to each of N configs (the old behaviour) could
    spend up to N times the intended budget in one invocation, with only the
    monthly guard bounding the total, and only between separate invocations.
    Each config's own cap is now the REMAINING budget when it starts, so the
    matrix as a whole can never exceed ``max_usd`` (bench_max_usd() when
    unset). A config starting with zero (or negative, from float rounding)
    remaining budget is skipped entirely rather than run — it would abort on
    its own first item anyway (harness's own cap<=0 short-circuit), but
    skipping makes the reason explicit in that config's row instead of a
    bare zero-item aborted result.

    A config whose runner errors on every item simply scores 0 — one broken
    configuration never aborts the rest of the matrix.
    """
    from .harness import bench_max_usd

    total_budget = max_usd if max_usd is not None else bench_max_usd()
    spent = 0.0
    rows: List[Dict[str, Any]] = []
    for config in configs:
        remaining = round(total_budget - spent, 6)
        if remaining <= 0:
            rows.append(
                {
                    "config": config.name,
                    "kind": config.kind,
                    "items_run": 0,
                    "pass_rate": 0.0,
                    "cost_usd": 0.0,
                    "cost_known": False,
                    "quality_per_dollar": None,
                    "aborted": (
                        f"matrix_budget_exhausted: ${spent:.2f} of ${total_budget:.2f} "
                        "total already spent by earlier configs — skipped, not run"
                    ),
                }
            )
            continue
        try:
            # _default_runner validates config.kind and parses config.name
            # (e.g. "solo:<model>") EAGERLY, before any item runs — a
            # malformed name (no colon) or an unknown kind raises here, not
            # inside harness's own per-item try/except. Uncaught, that would
            # crash the WHOLE matrix mid-run and discard already-PAID-FOR
            # results from every earlier config (round 1 review) — exactly
            # the failure mode the docstring promises never happens ("one
            # broken configuration never aborts the rest of the matrix").
            runner = config.runner or _default_runner(config)
            run = await run_bench(
                dataset_dir=dataset_dir,
                runs_dir=runs_dir,
                max_usd=remaining,
                items_filter=items_filter,
                council_runner=runner,
                ignore_score_floor=(config.kind == "solo"),
            )
        except Exception as exc:
            rows.append(
                {
                    "config": config.name,
                    "kind": config.kind,
                    "items_run": 0,
                    "pass_rate": 0.0,
                    "cost_usd": 0.0,
                    "cost_known": False,
                    "quality_per_dollar": None,
                    "aborted": f"config_error: {exc}",
                }
            )
            continue
        # cap_charged_usd (actuals + conservative unknown-cost charges), not
        # total_cost_usd — same convention as the monthly ledger (#439 r2/r3):
        # an unknown-cost config must still count against the shared budget,
        # not silently look free to the configs that follow it.
        spent = round(spent + run.cap_charged_usd, 6)
        # Consistent with BenchRun.exit_code (#507): pass rate excludes
        # council/infra-errored items, which never had a chance to score — an
        # infra-heavy config must not look artificially worse in the
        # quality-per-dollar comparison than one that simply ran cleanly.
        pass_rate = (
            round(run.items_passed / run.items_scored, 3) if run.items_scored else 0.0
        )
        rows.append(
            {
                "config": config.name,
                "kind": config.kind,
                "items_run": run.items_run,
                "pass_rate": pass_rate,
                "cost_usd": run.total_cost_usd,
                "cost_known": run.cost_known,
                "quality_per_dollar": quality_per_dollar(
                    pass_rate=pass_rate,
                    cost_usd=run.total_cost_usd,
                    cost_known=run.cost_known,
                ),
                "aborted": run.aborted,
            }
        )
    return rows


def format_matrix_table(rows: List[Dict[str, Any]]) -> str:
    """Markdown quality-per-dollar table."""
    lines = [
        "# Quality per Dollar (ADR-048 P2)",
        "",
        "| config | kind | items | pass rate | cost (USD) | quality/$ |",
        "|--------|------|-------|-----------|------------|-----------|",
    ]
    for r in rows:
        cost = f"{r['cost_usd']:.4f}" if r["cost_known"] else f"~{r['cost_usd']:.4f} (unknown)"
        qpd = r["quality_per_dollar"]
        qpd_str = f"{qpd:.3f}" if qpd is not None else "n/a"
        note = " (aborted)" if r.get("aborted") else ""
        lines.append(
            f"| {r['config']}{note} | {r['kind']} | {r['items_run']} "
            f"| {r['pass_rate']:.0%} | {cost} | {qpd_str} |"
        )
    lines.append("")
    lines.append(
        "Methodology & caveats: bench/METHODOLOGY.md (fixed judge config, "
        "ADR-047 calibration caveats, ADR-011 cost semantics)."
    )
    return "\n".join(lines)
