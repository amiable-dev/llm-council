#!/usr/bin/env python3
"""Emit council's `external` spans through the real OTel SDK and dump OTLP JSON.

Feeds `stdtel-conform`, the upstream checker, which reads the exporter's
`resourceSpans` shape:

    uv run python scripts/dump_external_spans.py > spans.json
    uvx --from "git+https://github.com/amiable-dev/skills-telemetry@main" \\
        stdtel-conform spans.json

ADR-056 is explicit that this checker is a **second opinion**, not the gate.
`tests/test_issue695_external_spend.py` is the gate: if the checker is missing,
lagging or itself wrong, council's build must still fail correctly.

The spans are produced by the same `build_span_attributes` the emitter uses and
recorded through a real `TracerProvider`, so this exercises span creation rather
than re-describing it. Only the serialisation is done here, because the OTLP
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

from llm_council.observability.external_spend import (  # noqa: E402
    SPAN_NAME,
    build_span_attributes,
)


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
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "llm-council"}}
                    ]
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

    # One consult and one verify, which is what #695's acceptance criteria name.
    # A provider-reported cost on both, because the checker reports cost
    # coverage separately: a shape-only pass over spans with no cost would tell
    # us nothing about the thing the contract exists to carry.
    cases = [
        (
            "consult",
            {
                "total": {
                    "prompt_tokens": 12000,
                    "completion_tokens": 3400,
                    "total_tokens": 15400,
                    "cached_tokens": 800,
                    "cache_write_tokens": 1200,
                    "cost_usd": 0.1837,
                    "cost_known": True,
                    "cost_source": "provider",
                },
                "by_model": {"a/one": {}, "b/two": {}, "c/three": {}, "d/four": {}},
            },
            118_000,
            "anthropic/claude-opus-5",
        ),
        (
            "verify",
            {
                "total": {
                    "prompt_tokens": 31411,
                    "completion_tokens": 5876,
                    "total_tokens": 37287,
                    "cached_tokens": 0,
                    "cache_write_tokens": 7410,
                    "cost_usd": 0.0317,
                    "cost_known": True,
                    "cost_source": "provider",
                },
                "by_model": {"a/one": {}, "b/two": {}, "c/three": {}, "d/four": {}},
            },
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
