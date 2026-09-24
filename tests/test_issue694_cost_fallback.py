"""#694 — cost capture must have a fallback, and the gateway must not drop it.

Cost coverage looked like 100% only because OpenRouter volunteers `usage.cost`
and the default path copies it through. Two things made that more fragile than
the number suggested.

## 1. The gateway path discards what its own resolver computed

`gateway/openrouter.py` and `gateway/requesty.py` already stamp `cost_usd` and
`cost_source` onto `TokenUsage` via `CostResolver`. `gateway_adapter` then
converts `GatewayResponse` back into the council's dict shape and copies only
the three token counts — so the resolver's output is computed and thrown away.
Turning `gateways.enabled` on would have silently zeroed cost coverage.

It is worse than the ticket recorded: the same conversion also drops
`cached_tokens` and `cache_write_tokens`, so enabling the gateway would have
zeroed the ADR-049 D4 cache telemetry too.

## 2. The default path has no fallback at all

If a provider omits the cost, `cost_known` is never set and every model in the
session lands null — which matches the observed all-or-nothing pattern (2,698
sessions entirely null, 846 entirely known, zero mixed).

**The ticket's first suggestion — send an accounting flag asking OpenRouter to
include usage — is a verified no-op and is deliberately NOT implemented.** Per
OpenRouter's usage-accounting documentation, `usage: {include: true}` is
"deprecated and has no effect… usage details are now always included
automatically". Adding it would be a parameter the API ignores, inside a
payload the ADR-049 caching tests byte-compare. The real exposure is the
non-OpenRouter routes, and the answer there is the registry estimate.

## An estimate must never be mistaken for a measurement

A figure that cannot be told apart from a measurement is worse than no figure,
because it will be summed with real ones. Every cost therefore carries a
`cost_source`, and any user-facing total that mixes estimates says so.
"""

import pytest


class TestTheGatewayCarriesCostBack:
    """The resolver's output must survive the conversion back to council's
    dict shape, or the path that HAS a fallback is the one without a cost."""

    def _response(self, **usage_kwargs):
        from llm_council.gateway.types import GatewayResponse, UsageInfo
        from llm_council.gateway_adapter import STATUS_OK

        usage = UsageInfo(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            **usage_kwargs,
        )
        return GatewayResponse(
            content="hello",
            model="anthropic/claude-opus-5",
            status=STATUS_OK,
            latency_ms=42,
            usage=usage,
        )

    def test_provider_cost_and_source_survive(self):
        from llm_council.gateway_adapter import _gateway_response_to_dict

        result = _gateway_response_to_dict(
            self._response(cost_usd=0.0042, cost_source="provider")
        )
        assert result["usage"]["cost"] == pytest.approx(0.0042)
        assert result["usage"]["cost_source"] == "provider"

    def test_an_estimate_keeps_its_label_through_the_conversion(self):
        from llm_council.gateway_adapter import _gateway_response_to_dict

        result = _gateway_response_to_dict(
            self._response(cost_usd=0.0011, cost_source="registry_estimate")
        )
        assert result["usage"]["cost_source"] == "registry_estimate", (
            "an estimate that loses its label becomes indistinguishable from a "
            "measurement the moment it is summed"
        )

    def test_cache_read_tokens_survive_too(self):
        """Not in the ticket. `cached_tokens` IS on `UsageInfo` and IS dropped
        by the same conversion, so enabling the gateway would have zeroed the
        ADR-049 cache-hit telemetry as well as cost."""
        from llm_council.gateway_adapter import _gateway_response_to_dict

        result = _gateway_response_to_dict(self._response(cached_tokens=64))
        assert result["usage"]["cached_tokens"] == 64

    def test_cache_write_tokens_are_carried_once_the_gateway_captures_them(self):
        """A different defect from the one the ticket names, and worth stating
        precisely: `cache_write_tokens` was never *dropped* by the conversion,
        because `UsageInfo` never carried it. The gateway layer simply never
        captured it, so the ADR-049 D4 write-side accounting does not exist on
        that path at all. Adding the field keeps the gateway from being a
        cache-accounting regression waiting to be switched on."""
        from llm_council.gateway_adapter import _gateway_response_to_dict

        result = _gateway_response_to_dict(self._response(cache_write_tokens=128))
        assert result["usage"]["cache_write_tokens"] == 128

    def test_an_absent_cost_stays_absent_rather_than_becoming_zero(self):
        from llm_council.gateway_adapter import _gateway_response_to_dict

        result = _gateway_response_to_dict(self._response())
        assert result["usage"]["cost"] is None
        assert result["usage"].get("cost_source") is None


class TestTheDefaultPathFallsBackToTheRegistry:
    def test_a_provider_that_omits_cost_still_yields_a_labelled_estimate(self):
        from llm_council.openrouter import resolve_missing_cost

        usage = {"prompt_tokens": 1000, "completion_tokens": 1000, "cost": None}
        resolve_missing_cost(usage, model="anthropic/claude-opus-5")

        assert usage["cost"] is not None and usage["cost"] > 0
        assert usage["cost_source"] == "registry_estimate"

    def test_a_reported_cost_is_never_overwritten_by_an_estimate(self):
        """Provider ground truth wins unconditionally — it already includes
        any discount the registry cannot know about."""
        from llm_council.openrouter import resolve_missing_cost

        usage = {"prompt_tokens": 1000, "completion_tokens": 1000, "cost": 0.5}
        resolve_missing_cost(usage, model="anthropic/claude-opus-5")

        assert usage["cost"] == 0.5
        assert usage["cost_source"] == "provider"

    def test_a_reported_zero_is_ground_truth_not_a_missing_value(self):
        from llm_council.openrouter import resolve_missing_cost

        usage = {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.0}
        resolve_missing_cost(usage, model="anthropic/claude-opus-5")

        assert usage["cost"] == 0.0
        assert usage["cost_source"] == "provider"

    def test_an_unregistered_model_stays_unknown(self):
        """No pricing, no estimate. Inventing one would be the exact failure
        this ticket is about."""
        from llm_council.openrouter import resolve_missing_cost

        usage = {"prompt_tokens": 1000, "completion_tokens": 1000, "cost": None}
        resolve_missing_cost(usage, model="nobody/not-a-real-model")

        assert usage["cost"] is None
        assert usage.get("cost_source") is None

    def test_never_raises_into_the_call_path(self):
        from llm_council.openrouter import resolve_missing_cost

        usage = {"prompt_tokens": "nonsense", "cost": None}
        resolve_missing_cost(usage, model=None)  # must not raise
        assert usage["cost"] is None


class TestProvenanceReachesTheAggregates:
    def test_cost_source_is_aggregated_per_model(self):
        from llm_council.council_usage import _add_cost_to_usage

        bucket = {}
        _add_cost_to_usage(
            bucket, {"cost": 0.01, "cost_source": "provider"}, model="m"
        )
        assert bucket["by_model"]["m"]["cost_source"] == "provider"

    def test_mixing_sources_for_one_model_is_reported_as_mixed(self):
        """Stage 1 might be provider-reported and stage 2 estimated. Claiming
        either label for the sum would be false; `mixed` is the honest answer
        and keeps the estimated portion visible."""
        from llm_council.council_usage import _add_cost_to_usage

        bucket = {}
        _add_cost_to_usage(bucket, {"cost": 0.01, "cost_source": "provider"}, model="m")
        _add_cost_to_usage(
            bucket, {"cost": 0.02, "cost_source": "registry_estimate"}, model="m"
        )
        assert bucket["by_model"]["m"]["cost_source"] == "mixed"
        assert bucket["by_model"]["m"]["cost_estimated_usd"] == pytest.approx(0.02)

    def test_the_estimated_portion_is_tracked_separately_from_the_total(self):
        from llm_council.council_usage import _add_cost_to_usage

        bucket = {}
        _add_cost_to_usage(bucket, {"cost": 0.01, "cost_source": "provider"})
        _add_cost_to_usage(bucket, {"cost": 0.04, "cost_source": "registry_estimate"})
        assert bucket["cost_usd"] == pytest.approx(0.05)
        assert bucket["cost_estimated_usd"] == pytest.approx(0.04)


class TestUserFacingTotalsShowTheSplit:
    def test_a_total_containing_an_estimate_says_so(self):
        from llm_council.cost_summary import format_cost_summary

        text = format_cost_summary(
            {
                "total": {
                    "total_tokens": 1000,
                    "cost_usd": 0.05,
                    "cost_estimated_usd": 0.04,
                    "cost_known": True,
                }
            }
        )
        assert "estimated" in text.lower(), (
            "a total that silently mixes an estimate with measurements is the "
            "failure mode this ticket names explicitly"
        )

    def test_a_fully_measured_total_is_not_cluttered_with_a_caveat(self):
        from llm_council.cost_summary import format_cost_summary

        text = format_cost_summary(
            {"total": {"total_tokens": 1000, "cost_usd": 0.05, "cost_known": True}}
        )
        assert "estimated" not in text.lower()


class TestEnablingTheGatewayDoesNotReduceCoverage:
    """The regression that is invisible until someone reconciles a bill."""

    def test_both_paths_report_a_cost_for_the_same_call(self):
        from llm_council.gateway.types import GatewayResponse, UsageInfo
        from llm_council.gateway_adapter import STATUS_OK, _gateway_response_to_dict
        from llm_council.openrouter import resolve_missing_cost

        # Default path: provider reported nothing, registry fills in.
        default_usage = {"prompt_tokens": 1000, "completion_tokens": 500, "cost": None}
        resolve_missing_cost(default_usage, model="anthropic/claude-opus-5")

        # Gateway path: the resolver already stamped the same estimate.
        gateway_dict = _gateway_response_to_dict(
            GatewayResponse(
                content="x",
                model="anthropic/claude-opus-5",
                status=STATUS_OK,
                latency_ms=1,
                usage=UsageInfo(
                    prompt_tokens=1000,
                    completion_tokens=500,
                    total_tokens=1500,
                    cost_usd=default_usage["cost"],
                    cost_source="registry_estimate",
                ),
            )
        )

        assert default_usage["cost"] is not None
        assert gateway_dict["usage"]["cost"] == pytest.approx(default_usage["cost"]), (
            "switching gateways.enabled on changed the recorded cost for an "
            "identical call"
        )
        assert (
            gateway_dict["usage"]["cost_source"] == default_usage["cost_source"]
        )


class TestTheDeprecatedAccountingFlagIsNotSent:
    def test_the_payload_does_not_carry_a_usage_include_flag(self):
        """Verified against OpenRouter's docs: `usage: {include: true}` is
        deprecated and has no effect. Sending it would be a parameter the API
        ignores, inside a payload the ADR-049 cache tests byte-compare."""
        from llm_council.gateway.openrouter import build_openrouter_payload

        payload = build_openrouter_payload(
            model="anthropic/claude-opus-5",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert "usage" not in payload, (
            "a deprecated no-op accounting flag was added to the payload"
        )


class TestEveryConversionSiteRoutesThroughOneHelper:
    """Round 1 of the gate found a THIRD hand-built copy of the usage mapping,
    in the gateway branch of `query_models_parallel` — the primary multi-model
    path, which stages 1 and 2 both use. The PR claimed to have fixed "both"
    sites. Patching the third would have left a fourth waiting to be written,
    so the mapping is now one function and this test is what keeps it that way.
    """

    def test_no_conversion_site_builds_the_mapping_by_hand(self):
        import ast
        import pathlib as _pathlib

        src = _pathlib.Path("src/llm_council/gateway_adapter.py")
        tree = ast.parse(src.read_text())

        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            # A dict that names the token counts IS a usage mapping. The only
            # one allowed to spell them out is the helper itself.
            if {"prompt_tokens", "completion_tokens", "total_tokens"} <= keys:
                offenders.append(node.lineno)

        helper = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_usage_to_dict"
        )
        inside_helper = {
            n.lineno for n in ast.walk(helper) if isinstance(n, ast.Dict)
        }
        stray = [line for line in offenders if line not in inside_helper]
        assert not stray, (
            f"gateway_adapter.py builds a usage dict by hand at line(s) {stray}. "
            f"Every conversion site must call `_usage_to_dict`, or cost and the "
            f"cache counters get dropped on whichever path was missed — which "
            f"is exactly what happened to `query_models_parallel`."
        )

    def test_the_parallel_path_carries_cost(self):
        """The site the gate found. Stages 1 and 2 both use this path."""
        from llm_council.gateway.types import UsageInfo
        from llm_council.gateway_adapter import _usage_to_dict

        got = _usage_to_dict(
            UsageInfo(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                cost_usd=0.003,
                cost_source="provider",
                cached_tokens=4,
                cache_write_tokens=8,
            )
        )
        assert got["cost"] == pytest.approx(0.003)
        assert got["cost_source"] == "provider"
        assert got["cached_tokens"] == 4
        assert got["cache_write_tokens"] == 8

    def test_absent_usage_still_yields_the_full_shape(self):
        """A consumer reading `usage["cost"]` must not KeyError just because the
        gateway returned no usage object."""
        from llm_council.gateway_adapter import _usage_to_dict

        got = _usage_to_dict(None)
        assert got["cost"] is None
        assert got["prompt_tokens"] == 0
        assert got["cache_write_tokens"] == 0


class TestTheFallbackUsesTheRouteItIsActuallyOn:
    """The fallback exists for the NON-OpenRouter routes, and hardcoded
    `gateway="openrouter"` — so it mislabelled provenance on exactly the routes
    it was written for, and `CostResolver` branches on gateway (`local_zero`
    for Ollama)."""

    def test_a_local_gateway_resolves_to_local_zero(self):
        from llm_council.openrouter import resolve_missing_cost

        usage = {"prompt_tokens": 1000, "completion_tokens": 100, "cost": None}
        resolve_missing_cost(usage, "llama3", gateway="ollama")
        assert usage["cost"] == 0.0
        assert usage["cost_source"] == "local_zero"

    def test_the_default_route_still_estimates_from_the_registry(self):
        from llm_council.openrouter import resolve_missing_cost

        usage = {"prompt_tokens": 1000, "completion_tokens": 100, "cost": None}
        resolve_missing_cost(usage, "anthropic/claude-opus-5", gateway="openrouter")
        assert usage["cost_source"] == "registry_estimate"


class TestProviderCountsAreCoercedNotTrusted:
    """Both of these could silently disable the whole #694 fallback: a float
    token count degraded to 0, and a non-numeric one raised inside
    `resolve_missing_cost`, was swallowed by its own soft-fail, and left the
    cost unresolved — a guard defeating the feature it guards."""

    def test_a_float_cache_write_count_is_kept(self):
        from llm_council.openrouter import _extract_cache_write_tokens

        assert _extract_cache_write_tokens({"cache_creation_input_tokens": 1024.0}) == 1024

    def test_a_non_numeric_cached_count_does_not_break_the_fallback(self):
        from llm_council.openrouter import resolve_missing_cost

        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "cached_tokens": "lots",
            "cost": None,
        }
        resolve_missing_cost(usage, "anthropic/claude-opus-5", gateway="openrouter")
        assert usage["cost"] is not None, (
            "a junk cached-token value silently disabled the cost fallback"
        )


class TestProviderTelemetryIsNeverTrusted:
    """Round 2 of the gate. Each case below was a live defect, and the first is
    the sharpest: round 1's validation covered the `cached_tokens` top-level
    field and left the NESTED fallback raw — which is the branch OpenRouter
    actually populates. A guard over the path that was not the problem."""

    def test_the_nested_cached_token_branch_is_validated_too(self):
        from llm_council.openrouter import _extract_cached_tokens

        assert _extract_cached_tokens({"prompt_tokens_details": {"cached_tokens": "lots"}}) == 0
        assert _extract_cached_tokens({"prompt_tokens_details": {"cached_tokens": 512.0}}) == 512
        assert _extract_cached_tokens({"prompt_tokens_details": {"cached_tokens": 512}}) == 512

    @pytest.mark.parametrize("container", ["a string", ["a", "list"], 7])
    def test_a_truthy_non_dict_container_does_not_raise(self, container):
        """`(x or {})` rescues only FALSY values. A truthy non-dict reached
        `.get(...)` and raised inside result construction, where the broad
        handler turned an already-billed success into STATUS_ERROR and discarded
        the content — losing a paid-for answer to a malformed telemetry field."""
        from llm_council.openrouter import (
            _extract_cache_write_tokens,
            _extract_cached_tokens,
        )

        assert _extract_cached_tokens({"prompt_tokens_details": container}) == 0
        assert _extract_cache_write_tokens({"cache_creation": container}) == 0

    @pytest.mark.parametrize(
        "bad", [True, False, -1, float("nan"), float("inf"), "0.02", None]
    )
    def test_an_unusable_provider_cost_is_not_stamped_as_ground_truth(self, bad):
        """The figure was copied through unchecked and then labelled
        `provider` — so a bool, a negative or a NaN became authoritative billing
        data, in the change whose whole purpose is cost integrity."""
        from llm_council.openrouter import resolve_missing_cost

        usage = {"prompt_tokens": 1000, "completion_tokens": 100, "cost": bad}
        resolve_missing_cost(usage, "anthropic/claude-opus-5", gateway="openrouter")
        assert usage["cost_source"] != "provider", (
            f"{bad!r} was accepted as a provider-reported cost"
        )
        # It falls through to the labelled estimate rather than poisoning a
        # total that reads as a bill.
        assert usage["cost_source"] == "registry_estimate"

    @pytest.mark.parametrize("good", [0.0, 0.0123, 12, 0])
    def test_a_usable_provider_cost_still_wins(self, good):
        from llm_council.openrouter import resolve_missing_cost

        usage = {"prompt_tokens": 1000, "completion_tokens": 100, "cost": good}
        resolve_missing_cost(usage, "anthropic/claude-opus-5", gateway="openrouter")
        assert usage["cost_source"] == "provider"
        assert usage["cost"] == pytest.approx(float(good))


class TestTheAdapterKeepsTheDiagnostic:
    def test_an_exception_with_no_message_still_names_its_type(self):
        """#594's defect, re-introduced in the gateway branch by the same commit
        that fixes it on the direct path. `str(e)` is the empty string for an
        exception constructed without a message."""
        import ast
        import pathlib as _pathlib

        src = _pathlib.Path("src/llm_council/gateway_adapter.py").read_text()
        assert '"error": str(e)' not in src, (
            "the gateway error branch reports a bare str(e), which is empty for "
            "an exception built without a message — the #594 defect"
        )
        ast.parse(src)  # still valid python


class TestTheOutermostContainerIsGuardedToo:
    """Round 3. Round 2 added `_as_mapping` for the NESTED containers and left
    the outermost one — `data.get("usage", {})` — which is the one every field
    passes through. `.get(k, {})` defaults only when the key is ABSENT, so
    `"usage": null` yields None and every subsequent `.get` raises, inside the
    block where the broad handler turns an already-billed success into
    STATUS_ERROR and discards the content."""

    @pytest.mark.parametrize("payload", [None, "a string", ["a", "list"], 7])
    def test_a_malformed_usage_container_does_not_lose_the_answer(self, payload):
        from llm_council.openrouter import _as_mapping

        assert _as_mapping(payload) == {}

    def test_the_call_path_uses_the_guard_not_a_get_default(self):
        import pathlib as _pathlib

        src = _pathlib.Path("src/llm_council/openrouter.py").read_text()
        assert 'data.get("usage", {})' not in src, (
            "the outermost usage container is read with a .get default, which "
            "does not guard a present-but-null value"
        )
        assert '_as_mapping(data.get("usage"))' in src


class TestEveryCountGoesThroughTheOneCoercion:
    """`_as_token_count`'s docstring says "ONE coercion for every count that
    reaches arithmetic". Round 3 found the three PRIMARY counts copied raw — an
    invariant stated and not applied, in the commit that stated it."""

    def test_the_primary_counts_are_coerced_in_the_source(self):
        import pathlib as _pathlib

        src = _pathlib.Path("src/llm_council/openrouter.py").read_text()
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            assert f'"{field}": usage.get("{field}", 0)' not in src, (
                f"{field} bypasses _as_token_count"
            )
            assert f'_as_token_count(usage.get("{field}"))' in src

    @pytest.mark.parametrize("bad", ["120", None, True, -5, [1]])
    def test_a_junk_count_becomes_zero_not_an_exception(self, bad):
        from llm_council.openrouter import _as_token_count

        assert _as_token_count(bad) == 0

    def test_an_unbounded_integer_does_not_raise(self):
        """`math.isfinite` on a huge int raises OverflowError converting to
        float, and that would be caught by the caller's broad handler and
        destroy a paid-for completion."""
        from llm_council.openrouter import _as_reported_cost, _as_token_count

        assert _as_token_count(10**400) > 0
        assert _as_reported_cost(10**400) is None


class TestTheAdapterAcceptsReasoningParams:
    """Not introduced here, but escalated to blocking by the gate: the module
    documents itself as the unified interface, and every entry point raised
    TypeError on a kwarg the direct implementations accept — the #365
    silent-parameter-drop class one layer up. Forwarded on the direct path,
    ignored on the gateway branch, which is stated in the source and tracked in
    #702 rather than left to be discovered."""

    def test_every_public_entry_point_accepts_it(self):
        """Enumerated from `__all__`, not from a hand-written list.

        Round 3 added the kwarg to three of the four entry points and wrote a
        comment claiming all of them; round 4 found the gap — on
        `query_models_with_progress`, the primary multi-model path. A test that
        listed the same three would have agreed with the comment and missed it,
        which is the whole lesson. Derive the list from the module, and a new
        entry point is covered the day it is added.
        """
        import inspect

        from llm_council import gateway_adapter

        entry_points = [
            name
            for name in gateway_adapter.__all__
            if name.startswith("query_")
            and inspect.iscoroutinefunction(getattr(gateway_adapter, name, None))
        ]
        assert len(entry_points) >= 4, f"expected the query_* surface, got {entry_points}"

        missing = [
            name
            for name in entry_points
            if "reasoning_params"
            not in inspect.signature(getattr(gateway_adapter, name)).parameters
        ]
        assert not missing, (
            f"{missing} raise TypeError on a kwarg the direct implementations "
            f"accept — the #365 silent-parameter-drop class, one layer up"
        )

    def test_the_count_clamp_applies_to_both_numeric_branches(self):
        """The int branch clamped to `_MAX_TOKENS` and the float branch did not,
        so 1e300 walked past the bound the docstring declares."""
        from llm_council.openrouter import _MAX_TOKENS, _as_token_count

        assert _as_token_count(10**400) == _MAX_TOKENS
        assert _as_token_count(1e300) == _MAX_TOKENS
        assert _as_token_count(1500.0) == 1500


class TestTheDiagnosticIsNotMangled:
    def test_a_message_ending_in_a_colon_survives(self):
        """Round 2 used `rstrip(": ")`, which strips a CHARACTER SET rather than
        a suffix, so a legitimate message ending in a colon or a space was
        silently truncated. My own bug, introduced fixing someone else's."""
        from llm_council.gateway_adapter import _error_detail

        assert _error_detail(ValueError("bad config:")) == "ValueError: bad config:"
        assert _error_detail(ValueError("")) == "ValueError"
        assert _error_detail(RuntimeError("  padded  ")) == "RuntimeError:   padded  "


class TestARejectedCostLosesItsLabel:
    def test_an_unusable_cost_does_not_keep_a_stale_provenance(self):
        from llm_council.openrouter import resolve_missing_cost

        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 100,
            "cost": float("nan"),
            "cost_source": "provider",
        }
        resolve_missing_cost(usage, "nobody/not-a-real-model", gateway="openrouter")
        assert usage["cost"] is None
        assert usage.get("cost_source") != "provider", (
            "an unresolved cost kept a `provider` label — the exact confusion "
            "cost_source exists to prevent"
        )


class TestAMalformedEnvelopeDoesNotCostTheAnswer:
    """The last unguarded subscript in the function. `data["choices"][0]["message"]`
    assumes the key exists, the list is non-empty and the entry is an object;
    a throw lands in the broad handler, which reports STATUS_ERROR and discards
    content that has already been billed."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [
            {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.01}},
            {"choices": [], "usage": {"cost": 0.01}},
            {"choices": None, "usage": {"cost": 0.01}},
            {"choices": "nonsense", "usage": {"cost": 0.01}},
            {"choices": [None], "usage": {"cost": 0.01}},
            {"choices": ["a string"], "usage": {"cost": 0.01}},
        ],
        ids=["no-choices", "empty", "null", "not-a-list", "null-entry", "str-entry"],
    )
    async def test_the_call_still_reports_ok_and_keeps_its_usage(self, payload):
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.openrouter import STATUS_OK, query_model_with_status

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = payload
        response.raise_for_status = MagicMock()

        with (
            patch("llm_council.openrouter.OPENROUTER_API_KEY", "test-key"),
            patch("httpx.AsyncClient") as client,
        ):
            client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=response
            )
            result = await query_model_with_status(
                "anthropic/claude-opus-5", [{"role": "user", "content": "hi"}]
            )

        assert result["status"] == STATUS_OK, (
            "a malformed envelope turned an already-billed call into an error "
            "and threw the response away"
        )
        assert result["usage"]["cost"] == pytest.approx(0.01), (
            "the cost was lost along with the answer"
        )


class TestCostSourceIsAlwaysPresent:
    """`_usage_to_dict` always emits the key; this function had three exits that
    did not. Low practical risk — everything here reads it with `.get` — but a
    stated invariant broken by the neighbouring function is the pattern that
    produced four review rounds."""

    @pytest.mark.parametrize(
        "usage,model",
        [
            ({"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.01}, "a/b"),
            ({"prompt_tokens": 10, "completion_tokens": 5, "cost": None}, None),
            ({"prompt_tokens": 10, "completion_tokens": 5, "cost": float("nan")}, None),
            ({"prompt_tokens": 10, "completion_tokens": 5, "cost": None}, "nobody/nope"),
            (
                {"prompt_tokens": 10, "completion_tokens": 5, "cost": None},
                "anthropic/claude-opus-5",
            ),
        ],
        ids=["reported", "no-model", "junk-cost", "unregistered", "estimated"],
    )
    def test_every_exit_leaves_the_key_set(self, usage, model):
        from llm_council.openrouter import resolve_missing_cost

        resolve_missing_cost(usage, model, gateway="openrouter")
        assert "cost_source" in usage, (
            "an exit path left cost_source absent, so the direct and gateway "
            "shapes disagree on whether the key exists"
        )
