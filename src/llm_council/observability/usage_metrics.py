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
    if not usage:
        return
    try:
        if adapter is None:
            from .metrics_adapter import get_metrics_adapter

            adapter = get_metrics_adapter()
        backend = getattr(adapter, "backend", None)
    except Exception as exc:  # telemetry must never break a run
        logger.debug("emit_usage_metrics: no adapter (ignored): %s", exc)
        return
    if backend is None:
        return

    # Isolate per-model so one bad row never drops the rest of the batch.
    for model, mu in (usage.get("by_model") or {}).items():
        try:
            model_str = str(model)
            # OTel `gen_ai.system` names the GenAI provider (e.g. "openai",
            # "anthropic"), which is the model id's prefix — not our app name.
            provider = model_str.split("/", 1)[0] if "/" in model_str else "unknown"
            base = {
                "gen_ai.request.model": model_str,
                "gen_ai.operation.name": "chat",
                "gen_ai.system": provider,
            }
            # Emit token histograms unconditionally (0 is a valid observation).
            backend.emit_histogram(
                TOKEN_USAGE_METRIC,
                float(mu.get("prompt_tokens", 0) or 0),
                {**base, "gen_ai.token.type": "input"},
            )
            backend.emit_histogram(
                TOKEN_USAGE_METRIC,
                float(mu.get("completion_tokens", 0) or 0),
                {**base, "gen_ai.token.type": "output"},
            )
            # Emit cost only when it was actually reported (never a phantom $0).
            if mu.get("cost_known") and mu.get("cost_usd") is not None:
                backend.emit_gauge(COST_METRIC, float(mu["cost_usd"]), base)
        except Exception as exc:
            logger.debug("emit_usage_metrics: skipping model %r (ignored): %s", model, exc)
            continue
