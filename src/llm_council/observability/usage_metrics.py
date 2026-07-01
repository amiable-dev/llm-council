"""Emit token/cost metrics using OpenTelemetry GenAI conventions (ADR-011 §3).

Consumes the council's ``metadata["usage"]`` block (see
``council._build_usage_summary``) and emits, via the existing MetricsAdapter
backend (StatsD/Prometheus/NoOp), metrics named per the OTel GenAI semantic
conventions so any OTLP-compatible sink (PostHog, Grafana, Datadog) ingests
them with zero custom mapping:

- ``gen_ai.client.token.usage`` — histogram, tagged ``gen_ai.token.type``
  (input|output), ``gen_ai.request.model``, ``gen_ai.operation.name``.
- ``llm_council.cost.usd`` — gauge (namespaced until a GenAI-standard cost
  metric stabilizes), tagged by model.

Never raises: telemetry must not break a council run (ADR-041).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TOKEN_USAGE_METRIC = "gen_ai.client.token.usage"
COST_METRIC = "llm_council.cost.usd"


def emit_usage_metrics(usage: Optional[Dict[str, Any]], adapter: Any = None) -> None:
    """Emit per-model OTel GenAI token/cost metrics from a usage summary.

    Args:
        usage: the ``metadata["usage"]`` dict (``by_stage``/``by_model``/``total``).
        adapter: a MetricsAdapter (defaults to the global one). Injectable for tests.
    """
    try:
        if not usage:
            return
        if adapter is None:
            from .metrics_adapter import get_metrics_adapter

            adapter = get_metrics_adapter()
        backend = getattr(adapter, "backend", None)
        if backend is None:
            return

        by_model = usage.get("by_model") or {}
        for model, mu in by_model.items():
            base = {
                "gen_ai.request.model": str(model),
                "gen_ai.operation.name": "chat",
                "gen_ai.system": "llm_council",
            }
            prompt_tokens = mu.get("prompt_tokens", 0) or 0
            completion_tokens = mu.get("completion_tokens", 0) or 0
            if prompt_tokens:
                backend.emit_histogram(
                    TOKEN_USAGE_METRIC,
                    float(prompt_tokens),
                    {**base, "gen_ai.token.type": "input"},
                )
            if completion_tokens:
                backend.emit_histogram(
                    TOKEN_USAGE_METRIC,
                    float(completion_tokens),
                    {**base, "gen_ai.token.type": "output"},
                )
            # Only emit cost when it was actually reported (never a phantom $0).
            if mu.get("cost_known") and mu.get("cost_usd") is not None:
                backend.emit_gauge(COST_METRIC, float(mu["cost_usd"]), base)
    except Exception as exc:  # telemetry must never break a run
        logger.debug("emit_usage_metrics failed (ignored): %s", exc)
