"""#707 — adopt the skills-telemetry external contract v2 (stdtel 0.5.0).

Contract v2 adds cost provenance: ``std.external.cost_source`` (``provider`` or
``local``) and ``std.external.cost_estimated_usd``. An estimate may now leave
the process, in its own attribute, so it no longer has to be dropped.

## Why these tests build usage through the real aggregators

#695 shipped the rule "only provider-reported cost is emitted", and its tests
passed. They passed because they hand-built a usage ``total`` that carried
``cost_source`` and ``cost_estimated_usd``. The real ``total``, assembled by
``_build_usage_summary``, carried neither: those keys only ever reached the
per-model buckets. So on every real consult and verify, the estimate guard read
keys that were never there, and an estimated cost would have gone out as
``std.external.cost_usd``, indistinguishable from a bill. It stayed latent only
because no endpoint was configured anywhere.

Every test below therefore builds its usage the way a run does, through
``_add_cost_to_usage`` then ``_build_usage_summary``. A hand-written dict here
would agree with the emitter's assumptions and prove nothing.
"""

import pytest

from llm_council.council_usage import _add_cost_to_usage, _build_usage_summary
from llm_council.observability import external_spend as ext


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    ext._reset_for_tests()
    yield
    ext._reset_for_tests()


def _call(cost, source, prompt=100, completion=50):
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "cost": cost,
        "cost_source": source,
    }


def _run(*calls_by_stage):
    """Build a usage summary exactly as an orchestrator does.

    Each positional argument is one stage: a list of ``(model, call)`` pairs.
    """
    by_stage = {}
    for index, calls in enumerate(calls_by_stage, start=1):
        bucket = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for model, call in calls:
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                bucket[key] += call[key]
            _add_cost_to_usage(bucket, call, model=model)
        by_stage[f"stage{index}"] = bucket
    return _build_usage_summary(by_stage)


def _span(summary):
    return ext.build_span_attributes(operation="consult", usage_summary=summary)


COST = "std.external.cost_usd"
SOURCE = "std.external.cost_source"
ESTIMATE = "std.external.cost_estimated_usd"


class TestTheRealTotalCarriesProvenance:
    """The aggregate the emitter reads must hold what the emitter reads."""

    def test_the_grand_total_carries_the_estimated_portion(self):
        summary = _run(
            [("a/one", _call(0.03, "provider")), ("b/two", _call(0.02, "registry_estimate"))]
        )
        assert summary["total"]["cost_estimated_usd"] == pytest.approx(0.02)

    def test_the_grand_total_carries_the_merged_source(self):
        summary = _run([("a/one", _call(0.03, "registry_estimate"))])
        assert summary["total"]["cost_source"] == "registry_estimate"

    def test_the_grand_total_merges_sources_across_stages(self):
        summary = _run(
            [("a/one", _call(0.03, "provider"))],
            [("a/one", _call(0.01, "registry_estimate"))],
        )
        assert summary["total"]["cost_source"] == "mixed"
        assert summary["total"]["cost_estimated_usd"] == pytest.approx(0.01)

    def test_the_grand_total_knows_which_sources_it_saw(self):
        """`mixed` loses which sources were present, and the contract needs to
        know whether any of the observed part was provider-reported."""
        summary = _run(
            [("a/one", _call(0.03, "provider"))],
            [("b/two", _call(0.0, "local_zero")), ("c/three", _call(0.01, "registry_estimate"))],
        )
        assert set(summary["total"]["cost_sources"]) == {
            "provider",
            "local_zero",
            "registry_estimate",
        }

    def test_the_grand_total_carries_incompleteness(self):
        summary = _run([("a/one", _call(0.03, "provider")), ("b/two", _call(None, None))])
        assert summary["total"]["cost_incomplete"] is True


class TestEachCouncilSourceMapsOntoTheContract:
    """The mapping table in #707, one row per test."""

    def test_provider(self):
        attrs = _span(_run([("a/one", _call(0.04, "provider"))]))
        assert attrs[COST] == pytest.approx(0.04)
        assert attrs[SOURCE] == "provider"
        assert ESTIMATE not in attrs

    def test_a_provider_reported_zero_is_still_provider(self):
        """A fully cached call really cost nothing; the zero is a measurement,
        and it came from the provider."""
        attrs = _span(_run([("a/one", _call(0.0, "provider"))]))
        assert attrs[COST] == 0.0
        assert attrs[SOURCE] == "provider"

    def test_local_zero(self):
        attrs = _span(_run([("ollama/x", _call(0.0, "local_zero"))]))
        assert attrs[COST] == 0.0
        assert attrs[SOURCE] == "local"
        assert ESTIMATE not in attrs

    def test_an_estimate_only_run_sends_the_estimate_and_no_cost(self):
        """The bug this ticket found. Before the fix this span carried
        `cost_usd = 0.05`: an estimate presented as a bill."""
        attrs = _span(_run([("a/one", _call(0.05, "registry_estimate"))]))
        assert COST not in attrs, "an estimate reached std.external.cost_usd"
        assert SOURCE not in attrs, "cost_source is only sent alongside a cost_usd"
        assert attrs[ESTIMATE] == pytest.approx(0.05)

    def test_a_mixed_run_sends_only_the_observed_part_as_cost(self):
        """The checker cannot catch this one: 0.05 and 0.03 are both valid
        numbers. Only council knows 0.02 of the total was an estimate."""
        attrs = _span(
            _run(
                [("a/one", _call(0.03, "provider"))],
                [("a/one", _call(0.02, "registry_estimate"))],
            )
        )
        assert attrs[COST] == pytest.approx(0.03)
        assert attrs[SOURCE] == "provider"
        assert attrs[ESTIMATE] == pytest.approx(0.02)

    def test_observed_provider_and_local_is_provider(self):
        """The local part is a structural zero; the money came from a provider."""
        attrs = _span(
            _run([("a/one", _call(0.03, "provider")), ("ollama/x", _call(0.0, "local_zero"))])
        )
        assert attrs[COST] == pytest.approx(0.03)
        assert attrs[SOURCE] == "provider"

    def test_local_plus_estimate(self):
        attrs = _span(
            _run(
                [
                    ("ollama/x", _call(0.0, "local_zero")),
                    ("b/two", _call(0.02, "registry_estimate")),
                ]
            )
        )
        assert attrs[COST] == 0.0
        assert attrs[SOURCE] == "local"
        assert attrs[ESTIMATE] == pytest.approx(0.02)


class TestInternalVocabularyNeverLeaves:
    @pytest.mark.parametrize(
        "calls",
        [
            [("a/one", _call(0.04, "provider"))],
            [("ollama/x", _call(0.0, "local_zero"))],
            [("a/one", _call(0.05, "registry_estimate"))],
            [("a/one", _call(0.03, "provider")), ("b/two", _call(0.02, "registry_estimate"))],
        ],
    )
    def test_cost_source_is_only_ever_a_contract_value(self, calls):
        attrs = _span(_run(calls))
        if SOURCE in attrs:
            assert attrs[SOURCE] in ext.CONTRACT_COST_SOURCES
        assert "registry_estimate" not in attrs.values()
        assert "local_zero" not in attrs.values()
        assert "mixed" not in attrs.values()

    def test_the_contract_vocabulary_is_exactly_provider_and_local(self):
        # Longhand from `stdtel-conform --print-contract` (stdtel 0.5.0).
        assert ext.CONTRACT_COST_SOURCES == frozenset({"provider", "local"})


class TestUnobservedStaysOmitted:
    def test_no_estimate_means_no_estimate_attribute(self):
        """Never 0, never null: absent."""
        attrs = _span(_run([("a/one", _call(0.04, "provider"))]))
        assert ESTIMATE not in attrs

    def test_no_cost_reported_at_all_omits_everything(self):
        attrs = _span(_run([("a/one", _call(None, None))]))
        assert COST not in attrs
        assert SOURCE not in attrs
        assert ESTIMATE not in attrs

    def test_an_incomplete_observed_total_is_not_sent_as_the_cost(self):
        """A call reported no cost and the registry had no price for it. The
        observed sum is then a lower bound, and v2 has no attribute saying so,
        so sending it would present a lower bound as the total. #692 made the
        same call locally. Raised on #707 for a v3 completeness marker."""
        attrs = _span(_run([("a/one", _call(0.03, "provider")), ("b/two", _call(None, None))]))
        assert COST not in attrs
        assert SOURCE not in attrs


class TestTheVerifyPathUsesTheSameAggregate:
    def test_verify_builds_its_summary_with_build_usage_summary(self):
        """If verify ever grows its own summary builder, these tests stop
        covering it. Pin the dependency rather than assume it."""
        import inspect

        from llm_council.verification import api, pipeline

        # #720: the pipeline half of the split builds the summary.
        source = inspect.getsource(api) + inspect.getsource(pipeline)
        assert "_build_usage_summary(" in source


class TestTheLocalDisclosureWasVacuousToo:
    def test_a_real_run_with_an_estimate_says_so_in_the_cost_summary(self):
        """#694 added "(incl. ~$X estimated)" to the cost line. It read
        `total.cost_estimated_usd`, which the real total never carried, so the
        disclosure appeared in its unit test and on no actual run."""
        from llm_council.cost_summary import format_cost_summary

        summary = _run(
            [("a/one", _call(0.03, "provider")), ("b/two", _call(0.02, "registry_estimate"))]
        )
        assert "estimated" in format_cost_summary(summary)


class TestTheDriftCheckDetectsDrift:
    """`scripts/check_external_contract.py` runs in CI against the live
    `--print-contract`. These feed it the recorded v2 output, then mutate it,
    so the checker is shown to fail rather than assumed to."""

    @pytest.fixture
    def check(self):
        import importlib.util
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "check_external_contract", root / "scripts" / "check_external_contract.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        contract = json.loads((root / "tests" / "fixtures" / "stdtel_contract_v2.json").read_text())
        return module.contract_drift, contract

    def test_the_recorded_v2_contract_matches(self, check):
        drift, contract = check
        assert drift(contract) == []

    def test_a_renamed_attribute_is_detected_both_ways(self, check):
        drift, contract = check
        contract["attributes"] = [
            "std.external.request_count" if a == "std.external.requests" else a
            for a in contract["attributes"]
        ]
        problems = " ".join(drift(contract))
        assert "std.external.requests" in problems
        assert "std.external.request_count" in problems

    def test_a_new_contract_version_is_detected(self, check):
        drift, contract = check
        contract["contract_version"] = 3
        assert any("contract_version" in p for p in drift(contract))

    def test_a_new_cost_source_is_detected(self, check):
        drift, contract = check
        contract["cost_sources"] = ["provider", "local", "invoice"]
        assert any("cost_sources" in p for p in drift(contract))

    def test_scope_keys_are_not_reported_as_missing(self, check):
        drift, contract = check
        assert any(a.startswith("std.scope.") for a in contract["attributes"])
        assert not any("std.scope" in p for p in drift(contract))


class TestGateRound1:
    """Council gate on #708, round 1 (2 critical, 4 major)."""

    @pytest.mark.parametrize("garbage", ["0.05", float("nan"), float("inf"), True, -0.01])
    def test_a_malformed_cost_is_not_a_measured_zero(self, garbage):
        """`_as_number` turns garbage into 0, and `cost_known` used to be set
        for anything that was not None, so a malformed figure went out as a
        provider-measured $0.00. Unusable is unobserved: the total is
        incomplete."""
        summary = _run([("a/one", _call(garbage, "provider"))])
        attrs = _span(summary)
        assert COST not in attrs
        assert summary["total"]["cost_incomplete"] is True

    @pytest.mark.parametrize("field", ["cached_tokens", "cache_write_tokens"])
    def test_a_string_cache_count_does_not_crash_a_billed_run(self, field):
        call = _call(0.01, "provider")
        call[field] = "10"
        summary = _run([("a/one", call)])
        assert summary["total"]["cost_usd"] == pytest.approx(0.01)

    def test_requests_counts_calls_not_distinct_models(self):
        """The same model in stages 1, 2 and 3 is three requests."""
        summary = _run(
            [("a/one", _call(0.01, "provider")), ("b/two", _call(0.01, "provider"))],
            [("a/one", _call(0.01, "provider")), ("b/two", _call(0.01, "provider"))],
            [("a/one", _call(0.01, "provider"))],
        )
        assert _span(summary)["std.external.requests"] == 5

    def test_the_observed_amount_never_depends_on_the_estimate_field(self):
        """Round 3 replaced "total minus estimate" with an observed amount the
        aggregate tracks itself. A corrupt estimate can neither leak into the
        cost nor subtract from it."""
        summary = _run([("a/one", _call(0.03, "provider"))])
        for corrupt in (0.05, "x", float("nan"), None):
            summary["total"]["cost_estimated_usd"] = corrupt
            assert _span(summary)[COST] == pytest.approx(0.03)

    def test_a_cost_with_no_provenance_is_omitted_and_logged(self, caplog):
        import logging

        with caplog.at_level(logging.DEBUG, logger=ext.logger.name):
            attrs = _span(_run([("a/one", _call(0.02, None))]))
        assert COST not in attrs
        assert "provenance" in caplog.text

    def test_a_zero_registry_estimate_is_still_reported(self):
        """A model the registry prices at zero was estimated, at zero. Omitting
        it would make it indistinguishable from no estimate at all."""
        attrs = _span(_run([("free/model", _call(0.0, "registry_estimate"))]))
        assert attrs[ESTIMATE] == 0.0
        assert COST not in attrs

    def test_a_session_id_must_be_exactly_a_uuid(self, monkeypatch):
        """Surrounding whitespace is stripped before matching, so a trailing
        newline yields the clean id; anything else around it is rejected."""
        sid = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid + "\n")
        assert ext.claude_session_id() == sid
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid + "\nx")
        assert ext.claude_session_id() is None


class TestGateRound2:
    """Council gate on #708, round 2 (1 critical, 6 major)."""

    def test_an_integer_too_large_for_a_float_does_not_crash_a_billed_run(self):
        """`math.isfinite(10**400)` raises OverflowError. JSON parses integers
        exactly, so a provider can send one."""
        call = _call(10**400, "provider")
        call["prompt_tokens"] = 10**400
        call["cached_tokens"] = 10**400
        summary = _run([("a/one", call)])
        assert summary["total"]["cost_incomplete"] is True
        assert COST not in _span(summary)

    def test_string_token_counts_still_reach_the_span(self):
        """A numeric string is coerced to 200.0 by the aggregate; the span
        used to accept only int and so dropped the attribute."""
        call = _call(0.01, "provider")
        call["cached_tokens"] = "200"
        summary = _run([("a/one", call)])
        assert _span(summary)["gen_ai.usage.cache_read_input_tokens"] == 200

    def test_negative_counts_are_not_emitted(self):
        summary = _run([("a/one", _call(0.01, "provider"))])
        summary["total"]["prompt_tokens"] = -5
        assert "gen_ai.usage.input_tokens" not in _span(summary)

    def test_grand_total_sums_survive_a_malformed_stage_bucket(self):
        summary = _build_usage_summary(
            {"stage1": {"prompt_tokens": "12", "completion_tokens": None, "cost_usd": "x"}}
        )
        assert summary["total"]["prompt_tokens"] == 12

    @pytest.mark.parametrize(
        "total",
        [
            {"cost_known": True, "cost_usd": 0.01, "cost_sources": 7},
            {"cost_known": True, "cost_usd": 0.01, "cost_source": ["provider"]},
            {"cost_known": True, "cost_usd": 0.01, "cost_source": {"a": 1}},
        ],
    )
    def test_a_malformed_total_never_raises(self, total):
        assert COST not in ext.cost_attributes({"total": total})

    def test_an_incomplete_run_sends_no_cost_attributes_at_all(self):
        """Both amounts of an incomplete run are lower bounds, and v2 cannot
        say so. The estimate is withheld for the same reason as the cost."""
        attrs = _span(
            _run([("a/one", _call(0.02, "registry_estimate")), ("b/two", _call(None, None))])
        )
        assert ESTIMATE not in attrs
        assert COST not in attrs

    def test_an_unknown_source_label_is_logged(self, caplog):
        import logging

        with caplog.at_level(logging.DEBUG, logger=ext.logger.name):
            attrs = _span(_run([("a/one", _call(0.02, "cache_hit"))]))
        assert COST not in attrs
        assert "provenance" in caplog.text

    def test_requests_are_omitted_rather_than_undercounted(self):
        """A total without the call counter is a hand-built shape; the
        distinct-model count it used to fall back to is knowingly wrong."""
        attrs = ext.build_span_attributes(
            operation="consult",
            usage_summary={"total": {}, "by_model": {"a": {}, "b": {}}},
        )
        assert "std.external.requests" not in attrs

    @pytest.mark.parametrize("bad", [True, -1, "12", float("nan")])
    def test_a_bad_duration_is_omitted_and_the_span_survives(self, bad):
        attrs = ext.build_span_attributes(
            operation="consult",
            usage_summary=_run([("a/one", _call(0.01, "provider"))]),
            duration_ms=bad,
        )
        assert "std.external.duration_ms" not in attrs
        assert attrs[COST] == pytest.approx(0.01)

    def test_health_check_needs_the_exporter_not_just_the_sdk(self, monkeypatch):
        """The SDK and the OTLP/HTTP exporter ship as separate distributions.
        With only the SDK every span is dropped, so the check must not say
        enabled."""
        import importlib.util

        real = importlib.util.find_spec

        def fake(name, *a, **k):
            if name.startswith("opentelemetry.exporter"):
                return None
            return real(name, *a, **k)

        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        monkeypatch.setattr(importlib.util, "find_spec", fake)
        status = ext.telemetry_status()
        assert status["enabled"] is False
        assert status["reason"] == "sdk_missing"

    def test_health_check_does_not_echo_credentials_in_the_endpoint(self, monkeypatch):
        monkeypatch.setenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "https://user:secret@collector.example:4318/x?token=t"
        )
        monkeypatch.setattr(ext, "_sdk_available", lambda: True)
        endpoint = ext.telemetry_status()["endpoint"]
        assert "secret" not in endpoint and "token" not in endpoint
        assert endpoint == "https://collector.example:4318"

    def test_the_contract_vocabulary_constant_is_what_the_mapping_emits(self):
        for calls in (
            [("a/one", _call(0.04, "provider"))],
            [("ollama/x", _call(0.0, "local_zero"))],
        ):
            assert _span(_run(calls))[SOURCE] in ext.CONTRACT_COST_SOURCES


class TestGateRound3:
    """Council gate on #708, round 3: provenance per amount, not per label set."""

    @pytest.mark.parametrize("stray", [None, "cache_hit", 7])
    def test_an_unattributed_amount_does_not_ride_in_as_provider_spend(self, stray, caplog):
        """One provider call used to make the WHOLE sum read as provider
        spend, including an amount that carried no label at all."""
        import logging

        with caplog.at_level(logging.DEBUG, logger=ext.logger.name):
            summary = _run(
                [("a/one", _call(0.03, "provider")), ("b/two", _call(0.02, stray))]
            )
            attrs = _span(summary)
        assert summary["total"]["cost_unattributed"] is True
        assert COST not in attrs
        assert SOURCE not in attrs
        assert "provenance" in caplog.text

    def test_a_non_zero_local_zero_is_not_local_spend(self):
        """`local_zero` asserts a structural zero. A positive figure under it
        is a contradiction, not an observation."""
        summary = _run([("ollama/x", _call(0.5, "local_zero"))])
        assert summary["total"]["cost_unattributed"] is True
        assert COST not in _span(summary)

    def test_the_observed_amount_is_tracked_by_the_aggregate(self):
        summary = _run(
            [("a/one", _call(0.03, "provider")), ("ollama/x", _call(0.0, "local_zero"))],
            [("b/two", _call(0.02, "registry_estimate"))],
        )
        assert summary["total"]["cost_observed_usd"] == pytest.approx(0.03)
        assert summary["by_model"]["a/one"]["cost_observed_usd"] == pytest.approx(0.03)

    def test_an_overflowing_estimate_does_not_suppress_the_rest(self):
        summary = _run([("a/one", _call(0.03, "provider"))])
        summary["total"]["cost_estimated_usd"] = 10**400
        attrs = _span(summary)
        assert attrs[COST] == pytest.approx(0.03)
        assert ESTIMATE not in attrs

    def test_a_negative_sub_millisecond_duration_is_not_a_measured_zero(self):
        attrs = ext.build_span_attributes(
            operation="consult",
            usage_summary=_run([("a/one", _call(0.01, "provider"))]),
            duration_ms=-0.4,
        )
        assert "std.external.duration_ms" not in attrs

    def test_a_count_beyond_int64_is_omitted(self):
        summary = _run([("a/one", _call(0.01, "provider"))])
        summary["total"]["prompt_tokens"] = 2**63
        assert "gen_ai.usage.input_tokens" not in _span(summary)

    def test_an_ipv6_endpoint_keeps_its_brackets(self, monkeypatch):
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://[::1]:4318")
        monkeypatch.setattr(ext, "_sdk_available", lambda: True)
        assert ext.telemetry_status()["endpoint"] == "http://[::1]:4318"

    def test_a_bare_string_of_sources_is_not_split_into_characters(self):
        from llm_council.council_usage import _note_cost_sources

        bucket = {}
        _note_cost_sources(bucket, "provider")
        assert bucket["cost_sources"] == ["provider"]


class TestGateRound4:
    """Council gate on #708, round 4 (PASS); its remaining majors were all on
    the hand-built-total fallback, which is removed rather than patched."""

    @pytest.mark.parametrize(
        "total",
        [
            # a provider-labelled total that also carries an estimate
            {"cost_known": True, "cost_source": "provider", "cost_usd": 5, "cost_estimated_usd": 2},
            # a non-zero local_zero
            {"cost_known": True, "cost_source": "local_zero", "cost_usd": 0.5},
        ],
    )
    def test_a_total_without_an_observed_amount_sends_no_cost(self, total):
        assert COST not in ext.cost_attributes({"total": total})

    def test_a_stored_bare_string_of_sources_is_not_split(self):
        from llm_council.council_usage import _note_cost_sources

        bucket = {"cost_sources": "provider"}
        _note_cost_sources(bucket, ["local_zero"])
        assert bucket["cost_sources"] == ["local_zero", "provider"]

    def test_an_incomplete_total_is_logged(self, caplog):
        import logging

        with caplog.at_level(logging.DEBUG, logger=ext.logger.name):
            _span(_run([("a/one", _call(0.03, "provider")), ("b/two", _call(None, None))]))
        assert "no usable cost" in caplog.text
