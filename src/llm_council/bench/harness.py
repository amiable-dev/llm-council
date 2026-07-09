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

import asyncio
import contextlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# File locking - use fcntl on Unix, fallback to no-op on Windows (same
# precedent as triage/rollback_metrics.py).
try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

logger = logging.getLogger(__name__)

DEFAULT_DATASET_DIR = Path("bench") / "dataset" / "v1"
DEFAULT_BASELINE_PATH = Path("bench") / "baseline.json"
DEFAULT_RUNS_DIR = Path(".council") / "bench" / "runs"

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_ABORTED = 2


@contextlib.asynccontextmanager
async def _monthly_guard_lock(runs_dir: Path) -> Any:
    """Serialize the monthly-guard check-through-persist section (#516).

    Without this, two concurrent ``bench run`` invocations (separate
    processes) can both read the same month-to-date spend, both pass the
    guard, then both write — jointly exceeding
    ``LLM_COUNCIL_BENCH_MONTHLY_USD`` (a time-of-check-to-time-of-use race).
    Concurrent bench runs aren't the documented usage ("on-demand or nightly,
    never per-PR"), so full mutual exclusion for the run's duration is an
    acceptable, simple fix rather than a partial/periodic re-check. Unix-only
    (fcntl); a no-op on Windows, matching the existing precedent in
    triage/rollback_metrics.py.

    ASYNC on purpose (round 6 review): ``fcntl.flock`` is a blocking syscall
    held across the ``await``s inside the guarded section. A plain
    synchronous acquire would, on contention, block the WHOLE event loop —
    not just the calling coroutine — freezing every other task in the
    process for as long as the lock is held (potentially minutes). No
    current call site runs two ``run_bench`` coroutines concurrently in one
    process (``bench matrix`` awaits them sequentially), so this cannot fire
    today, but the failure mode (a full event-loop freeze, not a clean
    queued wait) is bad enough to close categorically rather than leave as a
    footgun for a future concurrent caller. ``asyncio.to_thread`` moves the
    blocking acquire off the event loop thread so a contended lock merely
    suspends the awaiting coroutine.
    """
    if not _HAS_FCNTL:
        yield
        return
    runs_dir.mkdir(parents=True, exist_ok=True)
    lock_path = runs_dir / ".monthly-guard.lock"
    fh = open(lock_path, "a+")
    try:
        await asyncio.to_thread(fcntl.flock, fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


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
    # True when this item's failure is a council/infra error (runner raised, or
    # the council itself reported status="failed" — no responses/no synthesis),
    # not a genuine envelope/quality miss (#507). Keeps a rate-limit/billing
    # lapse from reading as "quality collapsed".
    is_infra: bool = False


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
    cap_usd: Optional[float] = None  # effective per-run cap (may be a --max-usd override)
    aborted: Optional[str] = None  # reason string when partial
    # True when --items scoped this run to a subset of the dataset (#517):
    # set_baseline must refuse a filtered run so the baseline never silently
    # loses coverage of the omitted items.
    filtered: bool = False
    # Count of items whose failure was a council/infra error, not a genuine
    # envelope miss (#507) — runner raised, or council reported status="failed"
    # (no responses / no synthesis). Kept separate so a rate-limit/billing
    # lapse can never read as "quality collapsed".
    infra_errors: int = 0
    results: List[ItemResult] = field(default_factory=list)

    @property
    def items_scored(self) -> int:
        """Items that actually ran through envelope scoring — excludes
        infra-errored items, which never produced a scoreable result."""
        return self.items_run - self.infra_errors

    @property
    def exit_code(self) -> int:
        if self.aborted:
            return EXIT_ABORTED
        # items_scored == 0 with items_run > 0 means EVERY attempted item was
        # an infra error — an infra/abort outcome, never a green pass (0 < 0
        # is False) and never drift (#507). _run_items already sets `aborted`
        # for this case, so `self.aborted` above should already catch it; this
        # is a defensive second layer in case a caller constructs a BenchRun
        # directly without going through _run_items.
        if self.items_run > 0 and self.items_scored == 0:
            return EXIT_ABORTED
        if self.items_passed < self.items_scored:
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


def _token_in_text(token: str, text: str) -> bool:
    """Case-insensitive any-of token match on WORD BOUNDARIES (#506).

    A bare substring test (the old behaviour) false-positives: ``"major"``
    matched ``"majority"``, ``"66"`` matched ``"1966"`` — a wrong answer could
    pass the envelope, silently weakening the drift guard. We anchor with ``\\b``
    only at edges adjacent to a word character, so punctuation-only tokens
    (``"?"``) and dotted tokens (``"os.system"``) still match by presence
    without an impossible boundary. ``text`` is expected pre-lowercased.
    """
    t = token.lower()
    if not t:
        return False
    # Lookarounds instead of \b so tokens whose edge char is non-word
    # (``"?"``, ``"c++"``) are still bounded correctly: require no word char
    # immediately adjacent on either side. \b would silently drop the boundary
    # on a punctuation edge, letting ``"c++"`` match inside ``"c++abc"``.
    return (
        re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text) is not None
    )


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
        if not any(_token_in_text(str(opt), text) for opt in options):
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
            except (OSError, ValueError) as exc:
                # A corrupt/unreadable artefact must NOT silently drop its spend
                # from a financial guard (that fails open, under-counting the
                # month-to-date total). Surface it loudly so the gap is visible
                # and actionable rather than invisible.
                logger.warning("bench: skipping unreadable run artefact %s: %s", f.name, exc)
                continue
            if not str(data.get("started_at", "")).startswith(prefix):
                continue
            # The guard sums cap_charged_usd (actuals + conservative unknown-cost
            # charges); fall back to total_cost_usd for pre-field artefacts. Guard
            # non-numeric/null values rather than crashing the whole tally.
            raw = data.get("cap_charged_usd")
            if raw is None:
                raw = data.get("total_cost_usd", 0.0)
            try:
                total += float(raw)
            except (TypeError, ValueError):
                logger.warning("bench: non-numeric spend in run artefact %s", f.name)
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
        known = {i.id for i in items}
        unknown = sorted(wanted - known)
        if unknown:
            # A typo'd / stale --items id must not silently drop to a green
            # "0/0 within envelope" run (#508). Fail loudly.
            raise ValueError(
                f"unknown --items id(s): {', '.join(unknown)}. "
                f"Available: {', '.join(sorted(known))}"
            )
        items = [i for i in items if i.id in wanted]

    run = BenchRun(
        started_at=datetime.now(timezone.utc).isoformat(),
        items_total=len(items),
        items_run=0,
        items_passed=0,
        total_cost_usd=0.0,
        cost_known=False,
        filtered=bool(items_filter),
    )

    if council_runner is None:
        from llm_council.council import run_council_with_fallback

        async def council_runner(prompt: str) -> Dict[str, Any]:  # pragma: no cover
            return await run_council_with_fallback(prompt, bypass_cache=True)

    resolved_runs_dir = runs_dir if runs_dir is not None else DEFAULT_RUNS_DIR
    # Hold the monthly-guard lock across check-through-persist (#516): without
    # this, two concurrent invocations can both read the same month-to-date
    # spend, both pass the guard, then both write — jointly exceeding the cap.
    async with _monthly_guard_lock(resolved_runs_dir):
        mtd = month_to_date_spend(runs_dir)
        if mtd >= monthly_cap:
            run.aborted = (
                f"monthly_guard: month-to-date bench spend ${mtd:.2f} >= "
                f"${monthly_cap:.2f} (LLM_COUNCIL_BENCH_MONTHLY_USD)"
            )
            _persist_run(run, runs_dir)
            return run
        return await _run_items(run, items, council_runner, cap, runs_dir, ignore_score_floor)


async def _run_items(
    run: "BenchRun",
    items: List[BenchItem],
    council_runner: Any,
    cap: float,
    runs_dir: Optional[Path],
    ignore_score_floor: bool,
) -> "BenchRun":
    """Execute the per-item loop and persist (split out of run_bench so the
    monthly-guard lock in run_bench wraps this whole section, #516)."""
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
            # An exception from the runner is unambiguously a council/infra
            # error (gateway down, transport failure), never a quality
            # signal (#507).
            run.results.append(
                ItemResult(
                    item_id=item.id,
                    domain=item.domain,
                    ok=False,
                    failures=[f"council_error:{exc}"],
                    is_infra=True,
                )
            )
            run.items_run += 1
            run.infra_errors += 1
            # An erroring item may already have spent (#439 r2): charge the
            # conservative default so failures cannot bypass the cap.
            cap_charged = round(cap_charged + bench_unknown_item_usd(), 6)
            any_unknown = True
            continue
        latency_ms = int((time.monotonic() - started) * 1000)
        synthesis = result.get("synthesis", "")
        score = _extract_score(result)
        cost, cost_known = _extract_cost(result)
        # The council itself may report total failure without raising (all
        # models errored/timed out — CLAUDE.md's graceful-degradation policy
        # returns a result with no responses rather than an exception). That
        # is ALSO a council/infra error, not a genuine envelope/quality miss
        # (#507's empirically-observed rate-limit case: score_unavailable at
        # $0.00 spend, every item failing — not a real quality regression).
        is_infra = result.get("metadata", {}).get("status") == "failed"
        if is_infra:
            failures = ["council_status_failed"]
        else:
            # Solo matrix configs (ADR-048 P2) have no council consensus
            # signal; min_score floors are skipped for them by explicit opt-in.
            failures = check_envelope(
                item, synthesis, score, apply_score_floor=not ignore_score_floor
            )
        run.total_cost_usd = round(run.total_cost_usd + cost, 6)
        cap_charged = round(cap_charged + (cost if cost_known else bench_unknown_item_usd()), 6)
        if not cost_known:
            any_unknown = True
        run.items_run += 1
        if is_infra:
            run.infra_errors += 1
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
                is_infra=is_infra,
            )
        )

    # An empty run (no items in the dataset, or every requested id filtered out)
    # must NOT read as a green exit-0 that set_baseline would then accept as the
    # reference — mark it aborted so exit is 2 and baselining refuses it (#508).
    if run.items_run == 0 and run.aborted is None:
        run.aborted = "no_items: 0 items ran (empty dataset or filter)"
    # Every attempted item was a council/infra error (rate-limit, billing
    # lapse, gateway down) — an infra/abort outcome, never a green pass
    # (items_scored==0 items_passed==0 would otherwise read as OK) or a
    # quality-drift signal (#507). A MIXED run (some infra, some genuinely
    # scored) is NOT aborted here — its exit reflects only the
    # genuinely-scored items via items_scored in exit_code.
    elif run.items_run > 0 and run.items_scored == 0 and run.aborted is None:
        run.aborted = (
            f"infra_failure: {run.infra_errors}/{run.items_run} items errored "
            "(council runner exception or status=failed) — not a quality signal"
        )
    # The between-item cap check never sees an overshoot caused by the FINAL
    # item (the loop just ends), so a run pushed over cap on its last item used
    # to complete as a silent exit-0. A run that reached its spend ceiling is an
    # aborted/partial outcome — record it so the breach is never silent (#510).
    if run.aborted is None and cap_charged >= cap:
        run.aborted = (
            f"per_run_cap: charged spend ${cap_charged:.2f} >= ${cap:.2f} "
            f"(LLM_COUNCIL_BENCH_MAX_USD; actuals ${run.total_cost_usd:.2f} + "
            f"unknown-cost charges) reached on the final item "
            f"({run.items_run}/{run.items_total} items)"
        )
    # 'fully known' means EVERY executed item reported a cost (#439 r2).
    run.cost_known = run.items_run > 0 and not any_unknown
    run.cap_charged_usd = cap_charged
    run.cap_usd = cap
    _persist_run(run, runs_dir)
    return run


def _persist_run(run: BenchRun, runs_dir: Optional[Path] = None) -> None:
    """Persist the run artefact (also feeds the monthly guard). Soft-fail."""
    directory = runs_dir if runs_dir is not None else DEFAULT_RUNS_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Keep microseconds and add the pid: a whole-second stamp collided so
        # two runs in the same second (e.g. `bench matrix` running configs
        # sequentially) wrote the same file — the second overwrote the first and
        # its spend vanished from the monthly ledger this feeds (#510).
        stamp = run.started_at.replace(":", "-").replace("+", "-")
        payload = asdict(run)
        payload["exit_code"] = run.exit_code
        (directory / f"run-{stamp}-{os.getpid()}.json").write_text(
            json.dumps(payload, indent=2)
        )
    except Exception as exc:
        logger.warning("bench run artefact not persisted (%s)", exc)


def set_baseline(run: BenchRun, baseline_path: Optional[Path] = None) -> Path:
    """Snapshot the run as the committed baseline.

    Refuses aborted/partial runs (#439 r3): a truncated run would bake an
    artificially narrow item set into the drift reference. Also refuses a
    ``--items``-filtered run (#517): baselining a subset silently shrinks
    coverage — the omitted items vanish from the drift reference and future
    regressions on them go undetected.
    """
    if run.aborted:
        raise ValueError(f"refusing to baseline an aborted run: {run.aborted}")
    if run.filtered:
        raise ValueError(
            "refusing to baseline a --items-filtered run "
            f"({run.items_run}/{run.items_total} items) — baseline against "
            "the full dataset so coverage never silently shrinks"
        )
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
    except OSError:
        return {"baseline": None}  # no baseline committed yet — expected, silent
    except json.JSONDecodeError as exc:
        # Corrupt baseline is NOT the same as "no baseline yet" — a silently
        # identical report for both hides real corruption from the operator
        # (round-5 review, same shape as #509's month_to_date_spend fix).
        logger.warning("bench: baseline file %s is corrupt: %s", path, exc)
        return {"baseline": None}
    regressions = []
    for r in run.results:
        if r.is_infra:
            # A council/infra error is NOT a quality regression (#507) — an
            # `ok=False` infra item would otherwise show up as a false
            # "regression vs baseline" here, exactly the drift-vs-infra
            # conflation #507 exists to prevent.
            continue
        base = baseline.get("items", {}).get(r.item_id)
        if base and base.get("ok") and not r.ok:
            regressions.append(r.item_id)
    # Consistent with exit_code (#507): pass rate excludes infra-errored
    # items, which never had a chance to score.
    pass_rate = round(run.items_passed / run.items_scored, 3) if run.items_scored else None
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
        f"Items: {run.items_passed}/{run.items_scored} within envelope "
        f"(of {run.items_total} selected) — exit code {run.exit_code}"
    )
    if run.infra_errors:
        # Surfaced separately from envelope drift (#507) — routes nightly
        # alerts to "check the gateway/billing" vs "quality regressed".
        lines.append(
            f"Council/infra errors: {run.infra_errors}/{run.items_run} "
            "(NOT a quality signal — see items marked [INFRA] below)"
        )
    cost = f"${run.total_cost_usd:.4f}" if run.cost_known else f"~${run.total_cost_usd:.4f} (cost not fully known)"
    # Show the EFFECTIVE cap (a --max-usd override), not the env default (#509).
    effective_cap = run.cap_usd if run.cap_usd is not None else bench_max_usd()
    lines.append(f"Spend: {cost} (per-run cap ${effective_cap:.2f})")
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
        marker = "PASS" if r.ok else ("INFRA" if r.is_infra else "FAIL")
        detail = "" if r.ok else f" — {'; '.join(r.failures)}"
        lines.append(f"- [{marker}] {r.item_id} ({r.domain}){detail}")
    return "\n".join(lines)
