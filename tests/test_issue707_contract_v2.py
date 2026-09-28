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

    def test_an_incomplete_run_still_reports_its_estimate(self):
        attrs = _span(
            _run([("a/one", _call(0.02, "registry_estimate")), ("b/two", _call(None, None))])
        )
        assert attrs[ESTIMATE] == pytest.approx(0.02)


class TestTheVerifyPathUsesTheSameAggregate:
    def test_verify_builds_its_summary_with_build_usage_summary(self):
        """If verify ever grows its own summary builder, these tests stop
        covering it. Pin the dependency rather than assume it."""
        import inspect

        from llm_council.verification import api

        source = inspect.getsource(api)
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

    def test_an_estimate_larger_than_the_total_sends_no_cost(self, caplog):
        """Not float residue: aggregation corruption. Publishing it as a
        measured 0.0 would hide it."""
        summary = _run([("a/one", _call(0.03, "provider"))])
        summary["total"]["cost_estimated_usd"] = 0.05
        attrs = _span(summary)
        assert COST not in attrs

    def test_float_residue_is_still_a_clean_zero(self):
        summary = _run([("ollama/x", _call(0.0, "local_zero"))])
        summary["total"]["cost_estimated_usd"] = 1e-18
        assert _span(summary)[COST] == 0.0

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
