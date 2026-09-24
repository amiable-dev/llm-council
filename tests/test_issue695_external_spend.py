"""#695 / ADR-056 — the external-spend contract, held from council's side.

`stdtel-conform` is a second opinion. **This file is the gate.** If their
checker is missing, lagging, or itself wrong, council's build still has to fail
correctly — otherwise council's correctness becomes contingent on another
project's release schedule.

## Why the allowlist is written out longhand below

An attribute outside the published `external` set is **dropped silently** by
the collector rather than rejected. So a rename — on either side — does not
produce an error; it produces a column of nulls nobody can date.

The obvious test, `assert EXTERNAL_ATTRIBUTES == EXTERNAL_ATTRIBUTES`, passes
through exactly that. So does asserting that a few known keys are present and a
few known-bad ones absent, which is what the upstream project's tests did
before #87: renaming `std.external.requests` would have satisfied all of them
while council kept sending the old key.

The set below is therefore transcribed by hand from
`skills-telemetry` `stdtel/artefact.py` at commit `3d93d8b`, and compared both
ways. An addition fails with "extend it"; a removal or rename fails with
"raise it on #695 first". `skills-telemetry` holds the mirror-image test.
"""

import os

import pytest

from llm_council.observability import external_spend as ext

# Transcribed by hand from stdtel/artefact.py @ 3d93d8b:
#   ALLOWED[KIND_EXTERNAL] = _COMMON | {external-specific keys}
# minus SCOPE_KEYS, which stdtel sets on receipt and an emitter must not send.
PUBLISHED_EXTERNAL_ATTRIBUTES = {
    # _COMMON
    "std.artefact.kind",
    "std.artefact.source",
    "session.id",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.cache_read_input_tokens",
    "gen_ai.usage.cache_creation_input_tokens",
    # KIND_EXTERNAL
    "std.artefact.name",
    "std.external.system",
    "std.external.operation",
    "std.external.cost_usd",
    "std.external.requests",
    "std.external.duration_ms",
    "gen_ai.request.model",
    "gen_ai.operation.name",
}

SCOPE_KEYS_SET_BY_STDTEL = {
    "std.scope.name",
    "std.scope.key",
    "std.scope.id",
    "std.scope.source",
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    ext._reset_for_tests()
    yield
    ext._reset_for_tests()


def _usage(cost=0.05, cost_known=True, **total_extra):
    total = {
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "total_tokens": 1500,
        "cached_tokens": 200,
        "cache_write_tokens": 100,
        "cost_usd": cost,
        "cost_known": cost_known,
    }
    total.update(total_extra)
    return {"total": total, "by_model": {"a/one": {}, "b/two": {}}}


class TestTheAllowlistMatchesThePublishedContract:
    def test_no_attribute_council_sends_is_outside_the_contract(self):
        extra = ext.EXTERNAL_ATTRIBUTES - PUBLISHED_EXTERNAL_ATTRIBUTES
        assert not extra, (
            f"council would send {sorted(extra)}, which the published external "
            f"contract does not carry. These are DROPPED SILENTLY downstream, "
            f"so the symptom is missing data rather than an error. Raise it on "
            f"#695 before adding an attribute."
        )

    def test_no_published_attribute_has_been_dropped_from_council(self):
        missing = PUBLISHED_EXTERNAL_ATTRIBUTES - ext.EXTERNAL_ATTRIBUTES
        assert not missing, (
            f"the published contract carries {sorted(missing)} and council's "
            f"constant does not. If the contract gained an attribute, extend "
            f"EXTERNAL_ATTRIBUTES. If it was renamed, council is still sending "
            f"the old key and the new column is silently null."
        )

    def test_scope_keys_are_not_ours_to_send(self):
        """`std.scope.*` is set by stdtel on receipt. An emitter sending it is
        asserting a scope it cannot know."""
        assert not (ext.EXTERNAL_ATTRIBUTES & SCOPE_KEYS_SET_BY_STDTEL)


class TestTheSpanSaysWhatItShould:
    def test_the_required_identity_attributes_are_present(self):
        attrs = ext.build_span_attributes(operation="consult", usage_summary=_usage())
        assert attrs["std.artefact.kind"] == "external"
        assert attrs["std.artefact.name"] == "llm-council"
        assert attrs["std.external.system"] == "llm-council"
        assert attrs["std.external.operation"] == "consult"
        assert attrs["gen_ai.operation.name"] == "chat"

    def test_source_is_emitter_never_hook_or_transcript(self):
        """`hook` claims the harness handed the value over; `transcript` claims
        stdtel inferred it from a session file. Nothing outside council's own
        process saw this spend, so either would assert an observation that
        never happened."""
        attrs = ext.build_span_attributes(operation="consult", usage_summary=_usage())
        assert attrs["std.artefact.source"] == "emitter"

    def test_the_operation_verb_is_bounded(self):
        with pytest.raises(ValueError):
            ext.build_span_attributes(
                operation="reviewed the performance store", usage_summary=_usage()
            )

    def test_token_counts_are_carried(self):
        attrs = ext.build_span_attributes(operation="verify", usage_summary=_usage())
        assert attrs["gen_ai.usage.input_tokens"] == 1000
        assert attrs["gen_ai.usage.output_tokens"] == 500
        assert attrs["gen_ai.usage.cache_read_input_tokens"] == 200
        assert attrs["gen_ai.usage.cache_creation_input_tokens"] == 100

    def test_every_attribute_emitted_is_in_the_allowlist(self):
        attrs = ext.build_span_attributes(
            operation="consult", usage_summary=_usage(), duration_ms=1234, model="a/one"
        )
        assert set(attrs) <= ext.EXTERNAL_ATTRIBUTES


class TestCostIsOmittedRatherThanFaked:
    def test_an_observed_cost_is_sent(self):
        attrs = ext.build_span_attributes(operation="consult", usage_summary=_usage(cost=0.07))
        assert attrs["std.external.cost_usd"] == pytest.approx(0.07)

    def test_an_observed_zero_is_sent_because_it_is_a_measurement(self):
        """A free tier or a fully cached response really did cost nothing."""
        attrs = ext.build_span_attributes(
            operation="consult", usage_summary=_usage(cost=0.0)
        )
        assert attrs["std.external.cost_usd"] == 0.0

    def test_an_unobserved_cost_omits_the_attribute_entirely(self):
        attrs = ext.build_span_attributes(
            operation="consult", usage_summary=_usage(cost=None, cost_known=False)
        )
        assert "std.external.cost_usd" not in attrs, (
            "an unobserved cost was sent as a value. Zero and null both read as "
            "measurements downstream; absence is the only honest encoding."
        )

    def test_a_registry_estimate_is_not_reported_as_spend(self):
        """ADR-056 D4. #694's estimate is honest locally, where it sits beside
        its `cost_source` label — but the external contract has no provenance
        attribute, so an estimate arriving as `std.external.cost_usd` is
        indistinguishable from a bill the moment a warehouse sums it."""
        attrs = ext.build_span_attributes(
            operation="consult",
            usage_summary=_usage(cost=0.05, cost_source="registry_estimate"),
        )
        assert "std.external.cost_usd" not in attrs

    def test_a_partly_estimated_total_is_not_reported_as_spend(self):
        attrs = ext.build_span_attributes(
            operation="consult",
            usage_summary=_usage(cost=0.05, cost_source="mixed", cost_estimated_usd=0.02),
        )
        assert "std.external.cost_usd" not in attrs


class TestSessionIdIsTheClaudeSession:
    def test_present_and_stamped_when_the_harness_exports_one(self, monkeypatch):
        session = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", session)
        attrs = ext.build_span_attributes(operation="consult", usage_summary=_usage())
        assert attrs["session.id"] == session

    def test_absent_outside_a_claude_session(self):
        """A CLI or CI run is real spend and still emits. Omitting the id is
        honest; inventing one produces rows that join to nothing."""
        attrs = ext.build_span_attributes(operation="consult", usage_summary=_usage())
        assert "session.id" not in attrs

    def test_a_councils_own_id_is_never_stamped_as_a_session(self, monkeypatch):
        """The verify path's id is an 8-char truncated UUID. Their checker
        rejects a `session.id` in the wrong shape precisely so this mistake
        fails loudly rather than joining to nothing."""
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "6bfbcb36")
        attrs = ext.build_span_attributes(operation="consult", usage_summary=_usage())
        assert "session.id" not in attrs


class TestNoContentEverLeaves:
    """ADR-056 D6. The check greps every value of every attribute, rather than
    asserting that particular keys are absent — a new attribute carrying
    content would pass a key-based check."""

    def test_a_recognisable_string_does_not_appear_in_any_attribute(self):
        canary = "CANARY-a7f3e9-the-users-actual-question"
        usage = _usage()
        usage["prompt"] = canary
        usage["total"]["question"] = canary
        usage["by_model"] = {canary: {}, "b/two": {}}

        attrs = ext.build_span_attributes(
            operation="consult", usage_summary=usage, model="a/one"
        )
        blob = " ".join(f"{k}={v}" for k, v in attrs.items())
        assert canary not in blob, (
            f"content leaked into the span: {blob}"
        )


class TestDisabledMeansInert:
    def test_no_endpoint_means_no_emission_and_no_tracer_construction(self, monkeypatch):
        """The claim is that an unconfigured install is byte-identical to
        pre-ADR-056 behaviour, and the load-bearing part of that is never
        reaching the SDK at all.

        Asserted by spying on `_get_tracer`, not by checking `sys.modules` —
        another test in the same session may legitimately have imported
        opentelemetry, so a `sys.modules` check would be flaky in one direction
        and vacuous in the other. (An earlier draft of this test wrote
        `assert ... or True`, which is a control reporting success over ground
        it never covered — the exact failure this file exists to prevent.)
        """
        called = []
        monkeypatch.setattr(ext, "_get_tracer", lambda: called.append(1))

        assert ext.external_spend_enabled() is False
        assert ext.emit_external_spend(operation="consult", usage_summary=_usage()) is False
        assert not called, "the tracer was constructed with no endpoint configured"

    def test_emission_never_raises(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1/v1/traces")
        # A malformed summary must not raise into a run that already completed.
        assert (
            ext.emit_external_spend(operation="consult", usage_summary="not a dict")
            is False
        )


class TestHealthCheckDistinguishesSilenceFromNothingSpent:
    """ADR-056 D8, raised by the skills-telemetry maintainer. A no-op emit path
    is right; saying nothing about it is not — a council with no extra
    installed would be indistinguishable from a council that spent nothing,
    which is the confusion #692 exists to end."""

    def test_unconfigured_is_reported_as_disabled_with_a_reason(self):
        status = ext.telemetry_status()
        assert status["enabled"] is False
        assert status["reason"] == "no_endpoint"
        assert "OTEL_EXPORTER_OTLP_ENDPOINT" in status["detail"]

    def test_configured_without_the_sdk_is_reported_distinctly(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
        monkeypatch.setattr(ext, "_sdk_available", lambda: False)
        status = ext.telemetry_status()
        assert status["enabled"] is False
        assert status["reason"] == "sdk_missing"
        assert "otel" in status["detail"]

    def test_fully_configured_is_reported_as_enabled(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
        monkeypatch.setattr(ext, "_sdk_available", lambda: True)
        status = ext.telemetry_status()
        assert status["enabled"] is True
        assert status["endpoint"] == "http://collector:4318"


def test_the_environment_is_not_mutated_by_import():
    """Importing the module must not configure anything."""
    assert os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") is None
