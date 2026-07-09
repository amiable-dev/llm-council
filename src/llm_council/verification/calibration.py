"""Confidence calibration from the verify transcript corpus (ADR-047 P2, #414).

Operational evidence (2026-07): on real code with zero blocking issues,
verify confidence pins at 0.90–1.00 for FAIL — over-confident rejections
that human disposition routinely overrode. This module makes confidence
mean something:

- ``analyze_corpus`` — reproducible summary over ``.council/logs`` (verdict/
  confidence distributions, the zero-blocking-FAIL anomaly rate).
- ``fit_from_dispositions`` — a simple monotonic (isotonic / PAV) mapping
  from raw confidence to observed P(verdict upheld), fitted against human
  dispositions recorded in ``.council/calibration/dispositions.jsonl``
  (``{"verification_id": ..., "upheld": true|false}`` per line).
- ``CalibrationMapping`` — piecewise-linear, monotonic, JSON-persisted at
  ``.council/calibration/mapping.json``; identity when absent.

Both confidences are surfaced on every response (``confidence`` raw,
``confidence_calibrated``). The PASS threshold uses the calibrated value
ONLY behind ``LLM_COUNCIL_CALIBRATED_CONFIDENCE=true`` (default off —
flag-off behaviour byte-identical) until the mapping is validated
(ADR-047 mitigation; modest-N observational data).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAPPING_PATH = Path(".council") / "calibration" / "mapping.json"
DEFAULT_DISPOSITIONS_PATH = Path(".council") / "calibration" / "dispositions.jsonl"
DEFAULT_LOGS_DIR = Path(".council") / "logs"


def calibrated_confidence_enabled() -> bool:
    """Flag gate: PASS thresholding uses calibrated confidence (default off)."""
    return os.getenv("LLM_COUNCIL_CALIBRATED_CONFIDENCE", "false").lower() in (
        "true",
        "1",
        "yes",
    )


@dataclass
class CalibrationRecord:
    """One verify outcome from the transcript corpus."""

    verification_id: str
    verdict: str
    confidence: Optional[float]
    blocking_count: int
    timeout_fired: bool


def load_corpus(logs_dir: Optional[Path] = None) -> List[CalibrationRecord]:
    """Read every ``result.json`` under the transcript logs. Soft-fail per file."""
    directory = logs_dir if logs_dir is not None else DEFAULT_LOGS_DIR
    records: List[CalibrationRecord] = []
    for result_file in sorted(directory.glob("*/result.json")):
        try:
            data = json.loads(result_file.read_text())
            records.append(
                CalibrationRecord(
                    verification_id=data.get("verification_id", result_file.parent.name),
                    # Normalize case defensively — the pipeline always writes
                    # lowercase, but the anomaly stats key on exact match.
                    verdict=str(data.get("verdict", "unclear")).lower(),
                    confidence=data.get("confidence"),
                    blocking_count=len(data.get("blocking_issues") or []),
                    timeout_fired=bool(data.get("timeout_fired")),
                )
            )
        except Exception as exc:
            logger.debug("skipping unreadable transcript %s (%s)", result_file, exc)
    return records


def analyze_corpus(records: List[CalibrationRecord]) -> Dict[str, Any]:
    """Reproducible corpus summary — the ADR-036 P2 calibration-report slice."""
    by_verdict: Dict[str, List[float]] = {}
    verdict_counts: Dict[str, int] = {}
    zero_blocking_fails = 0
    for r in records:
        # Count EVERY record's verdict — a null-confidence result must not
        # vanish from the histogram (#435 review); confidence stats
        # separately use only records that carry one.
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1
        if r.confidence is not None:
            by_verdict.setdefault(r.verdict, []).append(r.confidence)
        if r.verdict == "fail" and r.blocking_count == 0:
            zero_blocking_fails += 1
    fails = verdict_counts.get("fail", 0)
    summary: Dict[str, Any] = {
        "n": len(records),
        "verdicts": verdict_counts,
        "mean_confidence": {
            v: round(sum(cs) / len(cs), 3) for v, cs in by_verdict.items() if cs
        },
        # THE anomaly this ADR exists for: FAIL verdicts carrying no blocking
        # issue at all — high-confidence rejections with nothing to reject.
        "zero_blocking_fail_rate": round(zero_blocking_fails / fails, 3) if fails else None,
        "zero_blocking_fails": zero_blocking_fails,
    }
    return summary


def pav_fit(pairs: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Pool-adjacent-violators isotonic regression.

    Args:
        pairs: (raw_confidence, outcome) with outcome in [0, 1].

    Returns:
        Monotonic (x, y) breakpoints sorted by x (mean x/y per pooled block).
    """
    if not pairs:
        return []
    # Pre-aggregate tied x values (#435 r2): sorted() orders ties by y
    # ascending, so the strictly-greater merge below never pooled them —
    # leaving duplicate x breakpoints whose FIRST y won at lookup time.
    grouped: Dict[float, List[float]] = {}
    for x, y in pairs:
        grouped.setdefault(x, []).append(y)
    data = sorted((x, sum(ys), len(ys)) for x, ys in grouped.items())
    # blocks: [sum_y, count, sum_x]
    blocks: List[List[float]] = []
    for x, sum_y, n in data:
        blocks.append([sum_y, n, x * n])
        # Pool while the mean of the last block is below its predecessor's.
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            y2, n2, x2 = blocks.pop()
            blocks[-1][0] += y2
            blocks[-1][1] += n2
            blocks[-1][2] += x2
    return [(round(sx / n, 4), round(sy / n, 4)) for sy, n, sx in blocks]


@dataclass
class CalibrationMapping:
    """Piecewise-linear monotonic map raw→calibrated confidence."""

    points: List[Tuple[float, float]]  # sorted by x; empty => identity

    @classmethod
    def identity(cls) -> "CalibrationMapping":
        return cls(points=[])

    @property
    def is_identity(self) -> bool:
        return not self.points

    def calibrate(self, confidence: float) -> float:
        if not self.points:
            return round(max(0.0, min(1.0, confidence)), 2)
        pts = self.points
        if confidence <= pts[0][0]:
            return round(max(0.0, min(1.0, pts[0][1])), 2)
        if confidence >= pts[-1][0]:
            return round(max(0.0, min(1.0, pts[-1][1])), 2)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= confidence <= x1:
                if x1 == x0:
                    return round(max(0.0, min(1.0, y1)), 2)
                t = (confidence - x0) / (x1 - x0)
                return round(max(0.0, min(1.0, y0 + t * (y1 - y0))), 2)
        return round(max(0.0, min(1.0, confidence)), 2)  # pragma: no cover

    def to_json(self) -> str:
        return json.dumps({"version": 1, "points": self.points})

    @classmethod
    def from_json(cls, text: str) -> "CalibrationMapping":
        data = json.loads(text)
        points = [(float(x), float(y)) for x, y in data.get("points", [])]
        # Enforce monotonicity on load — a corrupt mapping must not invert.
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        if xs != sorted(xs) or ys != sorted(ys):
            raise ValueError("calibration mapping must be monotonic")
        return cls(points=points)


def fit_from_dispositions(
    records: List[CalibrationRecord],
    dispositions: Dict[str, bool],
) -> CalibrationMapping:
    """Fit the mapping against human dispositions.

    ``dispositions`` maps verification_id → whether the council's verdict was
    UPHELD by the eventual human decision (True) or overridden (False).
    Calibrated confidence estimates P(verdict upheld | raw confidence).
    """
    pairs: List[Tuple[float, float]] = []
    for r in records:
        if r.confidence is None or r.verification_id not in dispositions:
            continue
        pairs.append((r.confidence, 1.0 if dispositions[r.verification_id] else 0.0))
    if 0 < len(pairs) < 10:
        # ADR-047: modest-N observational data — the mapping is still fitted
        # (flag-gated adoption is the guard), but operators should know.
        logger.warning(
            "calibration fitted from only %d disposition pairs; treat as "
            "PRELIMINARY (ADR-047 validates before flag-on)",
            len(pairs),
        )
    return CalibrationMapping(points=pav_fit(pairs))


def load_dispositions(path: Optional[Path] = None) -> Dict[str, bool]:
    """Read the dispositions JSONL; soft-fail to empty."""
    p = path if path is not None else DEFAULT_DISPOSITIONS_PATH
    out: Dict[str, bool] = {}
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                upheld = row["upheld"]
                # Strict boolean only: bool("false") is True — coercing a
                # string would silently INVERT the disposition (#435 review).
                if not isinstance(upheld, bool):
                    logger.warning(
                        "disposition for %s has non-boolean upheld=%r; skipped",
                        row.get("verification_id"),
                        upheld,
                    )
                    continue
                out[str(row["verification_id"])] = upheld
            except Exception as exc:
                logger.warning("unparseable disposition line skipped (%s)", exc)
                continue
    except OSError:
        pass
    return out


def load_mapping(path: Optional[Path] = None) -> CalibrationMapping:
    """Load the persisted mapping; identity when absent/corrupt (soft-fail)."""
    p = path if path is not None else DEFAULT_MAPPING_PATH
    try:
        return CalibrationMapping.from_json(p.read_text())
    except Exception as exc:
        if p.exists():
            logger.warning("calibration mapping unreadable (%s); using identity", exc)
        return CalibrationMapping.identity()
