#!/usr/bin/env python3
"""Emit council's `external` spans through the real OTel SDK and dump OTLP JSON.

Feeds `stdtel-conform`, the upstream checker, which reads the exporter's
`resourceSpans` shape:

    uv run python scripts/dump_external_spans.py > spans.json
    uvx --from "stdtel==0.5.0" stdtel-conform spans.json

ADR-056 is explicit that this checker is a **second opinion**, not the gate.
`tests/test_issue695_external_spend.py` is the gate: if the checker is missing,
lagging or itself wrong, council's build must still fail correctly.

The spans are produced by the same `build_span_attributes` the emitter uses and
recorded through a real `TracerProvider`, so this exercises span creation rather
than re-describing it. The usage summaries are built through the real
`_add_cost_to_usage` / `_build_usage_summary`, never written by hand: a
hand-written total is what hid #707, where the real total lacked the
provenance keys the emitter read. Only the serialisation is done here, because the OTLP
HTTP exporter's encoder is private API and wants a live collector.
"""

from __future__ import annotations

import json
import sys

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

sys.path.insert(0, "src")

from llm_council.council_usage import (  # noqa: E402
    _add_cost_to_usage,
    _build_usage_summary,
)
from llm_council.observability.external_spend import (  # noqa: E402
    SPAN_NAME,
    build_span_attributes,
)


def _summary(*calls):
    """A usage summary built the way an orchestrator builds one.

    ``calls`` are ``(stage, model, prompt, completion, cached, cost, source)``.
    """
    by_stage = {}
    for stage, model, prompt, completion, cached, cost, source in calls:
        bucket = by_stage.setdefault(
            stage, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        )
        bucket["prompt_tokens"] += prompt
        bucket["completion_tokens"] += completion
        bucket["total_tokens"] += prompt + completion
        _add_cost_to_usage(
            bucket,
            {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
                "cached_tokens": cached,
                "cost": cost,
                "cost_source": source,
            },
            model=model,
        )
    return _build_usage_summary(by_stage)


def _otlp_value(value):
    """One attribute value in OTLP JSON's tagged-union encoding."""
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _to_resource_spans(spans):
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [{"key": "service.name", "value": {"stringValue": "llm-council"}}]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "llm_council.observability.external_spend"},
                        "spans": [
                            {
                                "name": span.name,
                                "startTimeUnixNano": str(span.start_time),
                                "endTimeUnixNano": str(span.end_time or span.start_time),
                                "attributes": [
                                    {"key": k, "value": _otlp_value(v)}
                                    for k, v in (span.attributes or {}).items()
                                ],
                            }
                            for span in spans
                        ],
                    }
                ],
            }
        ]
    }


def main() -> int:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer(__name__)

    # One run per contract row in #707: provider, local, estimate-only, mixed.
    # The checker reports estimate-only runs separately and does not count them
    # as reported, so a pass over provider-only spans would not exercise it.
    cases = [
        (
            "consult",
            _summary(
                ("stage1", "openai/gpt-5.6-sol", 4000, 1200, 800, 0.061, "provider"),
                ("stage1", "anthropic/claude-opus-5", 4000, 1100, 0, 0.074, "provider"),
                ("stage3", "anthropic/claude-opus-5", 4000, 1100, 0, 0.0487, "provider"),
            ),
            118_000,
            "anthropic/claude-opus-5",
        ),
        (
            "consult",
            _summary(("stage1", "ollama/llama4", 3000, 900, 0, 0.0, "local_zero")),
            42_000,
            "ollama/llama4",
        ),
        (
            "verify",
            _summary(
                (
                    "stage1",
                    "deepseek/deepseek-v4-pro-0813",
                    9000,
                    2000,
                    0,
                    0.0081,
                    "registry_estimate",
                ),
            ),
            61_000,
            "deepseek/deepseek-v4-pro-0813",
        ),
        (
            "verify",
            _summary(
                ("stage1", "openai/gpt-5.6-sol", 14000, 2600, 0, 0.0236, "provider"),
                (
                    "stage2",
                    "deepseek/deepseek-v4-pro-0813",
                    9000,
                    1500,
                    0,
                    0.0081,
                    "registry_estimate",
                ),
            ),
            135_064,
            "openai/gpt-5.6-sol",
        ),
    ]

    for operation, usage, duration_ms, model in cases:
        attrs = build_span_attributes(
            operation=operation,
            usage_summary=usage,
            duration_ms=duration_ms,
            model=model,
        )
        with tracer.start_as_current_span(SPAN_NAME) as span:
            span.set_attributes(attrs)

    provider.force_flush()
    json.dump(_to_resource_spans(exporter.get_finished_spans()), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
