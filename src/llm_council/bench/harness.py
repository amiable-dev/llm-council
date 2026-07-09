"""Golden-dataset drift regression harness (ADR-048 P1, #418).

Runs the versioned dataset (``bench/dataset/vN/``) against a configured
council, checks each result against its expected-quality envelope, and
compares aggregates to a committed baseline snapshot.

Cost discipline (ADR-048 council feedback — every run spends real money):
- hard per-run cap ``LLM_COUNCIL_BENCH_MAX_USD`` (default $2.00): checked
  against ACTUALS after every item; the run aborts gracefully at the cap
  with partial results marked partial (exit 2)
- month-to-date guard ``LLM_COUNCIL_BENCH_MONTHLY_USD`` (default $30):
  summed from run artefacts under ``.council/bench/runs/``; a run is
  refused before it starts when the month's spend already exceeds it
- runs are on-demand / scheduled only, NEVER per-PR

Exit codes: 0 within envelope, 1 drift beyond envelope, 2 aborted/partial.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DATASET_DIR = Path("bench") / "dataset" / "v1"
DEFAULT_BASELINE_PATH = Path("bench") / "baseline.json"
DEFAULT_RUNS_DIR = Path(".council") / "bench" / "runs"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_ABORTED = 2


def bench_max_usd() -> float:
    try:
        return float(os.getenv("LLM_COUNCIL_BENCH_MAX_USD", "2.00"))
    except ValueError:
        return 2.00


def bench_unknown_item_usd() -> float:
    """Conservative cap charge for items whose provider reported no cost
    (#439 review): counting unknown as $0 would make worst-case spend
    unbounded. Charged against CAP ACCOUNTING only — reported spend stays
    actuals, never fabricated (ADR-011)."""
    try:
        return float(os.getenv("LLM_COUNCIL_BENCH_UNKNOWN_ITEM_USD", "0.10"))
    except ValueError:
        return 0.10


def bench_monthly_usd() -> float:
    try:
        return float(os.getenv("LLM_COUNCIL_BENCH_MONTHLY_USD", "30.00"))
    except ValueError:
        return 30.00


@dataclass
class BenchItem:
    id: str
    domain: str
    prompt: str
    envelope: Dict[str, Any]


@dataclass
class ItemResult:
    item_id: str
    domain: str
    ok: bool
    failures: List[str] = field(default_factory=list)
    score: Optional[float] = None
    cost_usd: float = 0.0
    cost_known: bool = False
    latency_ms: int = 0


@dataclass
class BenchRun:
    started_at: str
    items_total: int
    items_run: int
    items_passed: int
    total_cost_usd: float
    cost_known: bool
    # Cap-accounting figure: actuals + conservative unknown-cost charges.
    # The monthly guard sums THIS, not raw actuals (#439 r3) — unknown-cost
    # runs must not erode the guard.
    cap_charged_usd: float = 0.0
    aborted: Optional[str] = None  # reason string when partial
    results: List[ItemResult] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if self.aborted:
            return EXIT_ABORTED
        if self.items_passed < self.items_run:
            return EXIT_DRIFT
        return EXIT_OK


def load_dataset(dataset_dir: Optional[Path] = None) -> List[BenchItem]:
    """Load and validate the dataset; raises on malformed items (fail fast —
    a broken dataset must not silently shrink coverage)."""
    directory = dataset_dir if dataset_dir is not None else DEFAULT_DATASET_DIR
    items: List[BenchItem] = []
    for f in sorted(directory.glob("*.json")):
        data = json.loads(f.read_text())
        for key in ("id", "domain", "prompt", "envelope"):
            if key not in data:
                raise ValueError(f"dataset item {f.name} missing '{key}'")
        items.append(
            BenchItem(
                id=data["id"],
                domain=data["domain"],
                prompt=data["prompt"],
                envelope=data["envelope"],
            )
        )
    if not items:
        raise ValueError(f"no dataset items found under {directory}")
    return items


def check_envelope(
    item: BenchItem,
    synthesis: str,
    score: Optional[float],
    apply_score_floor: bool = True,
) -> List[str]:
    """Return envelope violations (empty == within envelope)."""
    failures: List[str] = []
    text = (synthesis or "").lower()
    for group in item.envelope.get("must_contain", []):
        options = group if isinstance(group, list) else [group]
        if not any(str(opt).lower() in text for opt in options):
            failures.append(f"missing_any_of:{options}")
    min_score = item.envelope.get("min_score")
    if min_score is not None and apply_score_floor:
        if score is None:
            # A floor with no observable score IS drift (#439 r2): the
            # council stopped producing the signal the envelope guards.
            failures.append("score_unavailable")
        elif score < float(min_score):
            failures.append(f"score_below_floor({score}<{min_score})")
    return failures


def month_to_date_spend(runs_dir: Optional[Path] = None) -> float:
    """Sum bench spend recorded this calendar month from run artefacts."""
    directory = runs_dir if runs_dir is not None else DEFAULT_RUNS_DIR
    prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    total = 0.0
    try:
        for f in directory.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if str(data.get("started_at", "")).startswith(prefix):
                    total += max(
                        float(data.get("total_cost_usd", 0.0)),
                        float(data.get("cap_charged_usd", 0.0)),
                    )
            except Exception:
                continue
    except OSError:
        pass
    return total


def _extract_score(result: Dict[str, Any]) -> Optional[float]:
    """Top consensus average_score from the council metadata, if present."""
    try:
        rankings = result.get("metadata", {}).get("aggregate_rankings") or []
        if rankings:
            top = rankings[0].get("average_score")
            return float(top) if top is not None else None
    except Exception:
        pass
    return None


def _extract_cost(result: Dict[str, Any]) -> tuple:
    try:
        total = result.get("metadata", {}).get("usage", {}).get("total", {})
        return float(total.get("cost_usd", 0.0) or 0.0), bool(total.get("cost_known"))
    except Exception:
        return 0.0, False


async def run_bench(
    *,
    dataset_dir: Optional[Path] = None,
    items_filter: Optional[List[str]] = None,
    max_usd: Optional[float] = None,
    runs_dir: Optional[Path] = None,
    council_runner: Any = None,
    ignore_score_floor: bool = False,
) -> BenchRun:
    """Execute the bench. ``council_runner`` is injectable for tests
    (async callable prompt -> council result dict); the default runs the
    real council — REAL SPEND."""
    cap = max_usd if max_usd is not None else bench_max_usd()
    monthly_cap = bench_monthly_usd()
    items = load_dataset(dataset_dir)
    if items_filter:
        wanted = set(items_filter)
        items = [i for i in items if i.id in wanted]

    run = BenchRun(
        started_at=datetime.now(timezone.utc).isoformat(),
        items_total=len(items),
        items_run=0,
        items_passed=0,
        total_cost_usd=0.0,
        cost_known=False,
    )

    mtd = month_to_date_spend(runs_dir)
    if mtd >= monthly_cap:
        run.aborted = (
            f"monthly_guard: month-to-date bench spend ${mtd:.2f} >= "
            f"${monthly_cap:.2f} (LLM_COUNCIL_BENCH_MONTHLY_USD)"
        )
        _persist_run(run, runs_dir)
        return run

    if council_runner is None:
        from llm_council.council import run_council_with_fallback

        async def council_runner(prompt: str) -> Dict[str, Any]:  # pragma: no cover
            return await run_council_with_fallback(prompt, bypass_cache=True)

    # Cap accounting = actuals + conservative charges for unknown-cost items.
    # NOTE (by design): the cap is checked BETWEEN items, never mid-item —
    # a single item may overshoot; the abort is graceful, not mid-completion.
    cap_charged = 0.0
    any_unknown = False
    for item in items:
        if cap_charged >= cap:
            run.aborted = (
                f"per_run_cap: charged spend ${cap_charged:.2f} >= "
                f"${cap:.2f} (LLM_COUNCIL_BENCH_MAX_USD; actuals "
                f"${run.total_cost_usd:.2f} + unknown-cost charges) after "
                f"{run.items_run}/{run.items_total} items"
            )
            break
        started = time.monotonic()
        try:
            result = await council_runner(item.prompt)
        except Exception as exc:
            run.results.append(
                ItemResult(
                    item_id=item.id,
                    domain=item.domain,
                    ok=False,
                    failures=[f"council_error:{exc}"],
                )
            )
            run.items_run += 1
            # An erroring item may already have spent (#439 r2): charge the
            # conservative default so failures cannot bypass the cap.
            cap_charged = round(cap_charged + bench_unknown_item_usd(), 6)
            any_unknown = True
            continue
        latency_ms = int((time.monotonic() - started) * 1000)
        synthesis = result.get("synthesis", "")
        score = _extract_score(result)
        cost, cost_known = _extract_cost(result)
        # Solo matrix configs (ADR-048 P2) have no council consensus signal;
        # min_score floors are skipped for them by explicit opt-in.
        failures = check_envelope(
            item, synthesis, score, apply_score_floor=not ignore_score_floor
        )
        run.total_cost_usd = round(run.total_cost_usd + cost, 6)
        cap_charged = round(cap_charged + (cost if cost_known else bench_unknown_item_usd()), 6)
        if not cost_known:
            any_unknown = True
        run.items_run += 1
        if not failures:
            run.items_passed += 1
        run.results.append(
            ItemResult(
                item_id=item.id,
                domain=item.domain,
                ok=not failures,
                failures=failures,
                score=score,
                cost_usd=cost,
                cost_known=cost_known,
                latency_ms=latency_ms,
            )
        )

    # 'fully known' means EVERY executed item reported a cost (#439 r2).
    run.cost_known = run.items_run > 0 and not any_unknown
    run.cap_charged_usd = cap_charged
    _persist_run(run, runs_dir)
    return run


def _persist_run(run: BenchRun, runs_dir: Optional[Path] = None) -> None:
    """Persist the run artefact (also feeds the monthly guard). Soft-fail."""
    directory = runs_dir if runs_dir is not None else DEFAULT_RUNS_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = run.started_at.replace(":", "-").split(".")[0]
        payload = asdict(run)
        payload["exit_code"] = run.exit_code
        (directory / f"run-{stamp}.json").write_text(json.dumps(payload, indent=2))
    except Exception as exc:
        logger.warning("bench run artefact not persisted (%s)", exc)


def set_baseline(run: BenchRun, baseline_path: Optional[Path] = None) -> Path:
    """Snapshot the run as the committed baseline.

    Refuses aborted/partial runs (#439 r3): a truncated run would bake an
    artificially narrow item set into the drift reference.
    """
    if run.aborted:
        raise ValueError(f"refusing to baseline an aborted run: {run.aborted}")
    path = baseline_path if baseline_path is not None else DEFAULT_BASELINE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": run.started_at,
        "items": {
            r.item_id: {"ok": r.ok, "score": r.score, "cost_usd": r.cost_usd}
            for r in run.results
        },
        "pass_rate": round(run.items_passed / run.items_run, 3) if run.items_run else None,
        "total_cost_usd": run.total_cost_usd,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def compare_to_baseline(
    run: BenchRun, baseline_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Aggregate deltas vs the committed baseline; absent baseline => None."""
    path = baseline_path if baseline_path is not None else DEFAULT_BASELINE_PATH
    try:
        baseline = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        # Absent OR corrupt baseline (#439 review): report, never crash.
        return {"baseline": None}
    regressions = []
    for r in run.results:
        base = baseline.get("items", {}).get(r.item_id)
        if base and base.get("ok") and not r.ok:
            regressions.append(r.item_id)
    pass_rate = round(run.items_passed / run.items_run, 3) if run.items_run else None
    return {
        "baseline": baseline.get("created_at"),
        "baseline_pass_rate": baseline.get("pass_rate"),
        "pass_rate": pass_rate,
        "regressions": regressions,
    }


def format_report(run: BenchRun, comparison: Dict[str, Any], fmt: str = "md") -> str:
    if fmt == "json":
        payload = asdict(run)
        payload["exit_code"] = run.exit_code
        payload["comparison"] = comparison
        return json.dumps(payload, indent=2)
    lines = ["# Bench Report (ADR-048)"]
    lines.append(
        f"Items: {run.items_passed}/{run.items_run} within envelope "
        f"(of {run.items_total} selected) — exit code {run.exit_code}"
    )
    cost = f"${run.total_cost_usd:.4f}" if run.cost_known else f"~${run.total_cost_usd:.4f} (cost not fully known)"
    lines.append(f"Spend: {cost} (per-run cap ${bench_max_usd():.2f})")
    if run.aborted:
        lines.append(f"ABORTED (partial results): {run.aborted}")
    if comparison.get("baseline"):
        lines.append(
            f"Baseline {comparison['baseline']}: pass rate "
            f"{comparison.get('baseline_pass_rate')} -> {comparison.get('pass_rate')}"
        )
        if comparison.get("regressions"):
            lines.append(f"REGRESSIONS vs baseline: {', '.join(comparison['regressions'])}")
    else:
        lines.append("No committed baseline (run `llm-council bench baseline --set`).")
    for r in run.results:
        marker = "PASS" if r.ok else "FAIL"
        detail = "" if r.ok else f" — {'; '.join(r.failures)}"
        lines.append(f"- [{marker}] {r.item_id} ({r.domain}){detail}")
    return "\n".join(lines)
