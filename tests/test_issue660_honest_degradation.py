"""#660: a degraded consult result must not be presented with undegraded authority.

Field report (v0.45.1): a `high`-tier run lost 2 of 4 models to timeout — one of
them the chairman, which is also a council member — and returned one surviving
member's *raw response* under the heading ``### Chairman's Synthesis``, with the
"2 of 4 models" disclosure placed after the content as a footnote.

The heading was wrong twice: it was not a synthesis, and the chairman is what
failed. The survivor set is also biased rather than merely smaller — the models
that time out are the slowest, which are generally the strongest reasoners — so
a "2 of 4" footnote reads as a sampling caveat when it is a quality-selection
one.

These tests pin the honesty properties, not the prose: a caller must be able to
tell from the *heading* and from a machine-readable block what actually happened.
"""

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from llm_council import consult_render as render
from llm_council.council_stages import quick_synthesis

CHAIRMAN_HEADING = "### Chairman's Synthesis"


def _statuses(**models: str) -> Dict[str, Dict[str, Any]]:
    return {model: {"status": status} for model, status in models.items()}


COMPLETE = {
    "metadata": {
        "status": "complete",
        "synthesis_type": "full",
        "tier": "high",
        "requested_models": 4,
        "completed_models": 4,
    },
    "model_responses": _statuses(
        **{
            "openai/gpt-5.6-sol": "ok",
            "anthropic/claude-opus-5": "ok",
            "google/gemini-3.1-pro-preview": "ok",
            "deepseek/deepseek-v4-pro-0813": "ok",
        }
    ),
}

# The reported run: opus-5 and deepseek timed out; the chairman (opus-5) was one
# of them, so quick_synthesis fell back to a single member's raw response.
REPORTED_RUN = {
    "metadata": {
        "status": "partial",
        "synthesis_type": "single_model_raw",
        "tier": "high",
        "requested_models": 4,
        "completed_models": 2,
        "fallback_source_model": "openai/gpt-5.6-sol",
        "warning": (
            "This answer is based on 2 of 4 intended models. Did not respond: "
            "claude-opus-5 (timeout), deepseek-v4-pro-0813 (timeout)."
        ),
    },
    "model_responses": _statuses(
        **{
            "openai/gpt-5.6-sol": "ok",
            "anthropic/claude-opus-5": "timeout",
            "google/gemini-3.1-pro-preview": "ok",
            "deepseek/deepseek-v4-pro-0813": "timeout",
        }
    ),
}


class TestHeadingReflectsOutcome:
    """F1a: the heading is a function of what happened, not a constant."""

    def test_complete_run_keeps_the_chairman_heading(self):
        assert (
            render.synthesis_heading(COMPLETE["metadata"], COMPLETE["model_responses"])
            == CHAIRMAN_HEADING
        )

    def test_single_model_fallback_is_not_called_a_chairman_synthesis(self):
        heading = render.synthesis_heading(
            REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"]
        )
        assert CHAIRMAN_HEADING not in heading
        # Wrong twice: not a synthesis, and not the chairman's.
        assert "synthesis" not in heading.lower()
        assert "chairman" not in heading.lower() or "unavailable" in heading.lower()

    def test_single_model_fallback_names_the_model_and_the_shortfall(self):
        heading = render.synthesis_heading(
            REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"]
        )
        assert "openai/gpt-5.6-sol" in heading
        assert "2" in heading and "4" in heading

    def test_partial_synthesis_declares_the_shortfall(self):
        metadata = {**REPORTED_RUN["metadata"], "synthesis_type": "partial"}
        metadata.pop("fallback_source_model")
        heading = render.synthesis_heading(metadata, REPORTED_RUN["model_responses"])
        assert CHAIRMAN_HEADING not in heading
        assert "2" in heading and "4" in heading

    def test_partial_synthesis_says_peer_review_did_not_run(self):
        """The quick_synthesis path skips stage 2 entirely — a council without
        peer review is not the product the caller asked for."""
        metadata = {**REPORTED_RUN["metadata"], "synthesis_type": "partial"}
        heading = render.synthesis_heading(metadata, REPORTED_RUN["model_responses"])
        assert "peer review" in heading.lower()

    def test_full_synthesis_over_fewer_members_stays_a_synthesis_but_says_so(self):
        """Stage 2 ran; only the membership was short. That IS a chairman
        synthesis, so it keeps the name — with the shortfall attached."""
        metadata = {
            **REPORTED_RUN["metadata"],
            "synthesis_type": "full",
            "completed_models": 3,
        }
        heading = render.synthesis_heading(metadata, REPORTED_RUN["model_responses"])
        assert "Chairman" in heading
        assert "3" in heading and "4" in heading

    def test_total_failure_is_labelled_a_failure(self):
        metadata = {
            "status": "failed",
            "synthesis_type": "none",
            "requested_models": 4,
            "completed_models": 0,
        }
        heading = render.synthesis_heading(metadata, {})
        assert "fail" in heading.lower()
        assert CHAIRMAN_HEADING not in heading

    def test_missing_metadata_never_claims_a_complete_council(self):
        """Absent status must not be read as success — fail honest, not silent."""
        heading = render.synthesis_heading({}, {})
        assert CHAIRMAN_HEADING not in heading


class TestMachineReadableStatus:
    """F1c: a caller must be able to branch on partial without parsing prose."""

    def test_status_block_is_parseable_json(self):
        block = render.status_block(REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"])
        payload = json.loads(re.search(r"```json\n(.*?)\n```", block, re.S).group(1))
        assert payload["status"] == "partial"
        assert payload["synthesis_type"] == "single_model_raw"
        assert payload["models_responded"] == 2
        assert payload["models_requested"] == 4
        assert payload["tier"] == "high"

    def test_status_block_reports_whether_peer_review_ran(self):
        degraded = json.loads(
            re.search(
                r"```json\n(.*?)\n```",
                render.status_block(REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"]),
                re.S,
            ).group(1)
        )
        assert degraded["peer_review"] is False

        complete = json.loads(
            re.search(
                r"```json\n(.*?)\n```",
                render.status_block(COMPLETE["metadata"], COMPLETE["model_responses"]),
                re.S,
            ).group(1)
        )
        assert complete["peer_review"] is True

    def test_status_block_names_each_failed_model_and_why(self):
        payload = json.loads(
            re.search(
                r"```json\n(.*?)\n```",
                render.status_block(REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"]),
                re.S,
            ).group(1)
        )
        failed = {entry["model"]: entry["status"] for entry in payload["failed_models"]}
        assert failed == {
            "anthropic/claude-opus-5": "timeout",
            "deepseek/deepseek-v4-pro-0813": "timeout",
        }

    def test_status_block_is_emitted_for_complete_runs_too(self):
        """Conditional presence is what forces callers back to parsing prose."""
        assert "```json" in render.status_block(COMPLETE["metadata"], COMPLETE["model_responses"])


class TestDegradationComesFirst:
    """F1b: the notice precedes the content it qualifies."""

    def test_notice_precedes_the_synthesis_body(self):
        body = "Here is a confident, well-structured answer."
        out = render.render_consult_body(
            REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"], body
        )
        assert out.index("2 of 4") < out.index(body)

    def test_complete_run_has_no_degradation_notice(self):
        body = "A real synthesis."
        out = render.render_consult_body(COMPLETE["metadata"], COMPLETE["model_responses"], body)
        assert "Note" not in out.split(body)[0]

    def test_body_is_never_dropped(self):
        body = "content that must survive rendering"
        for case in (COMPLETE, REPORTED_RUN):
            out = render.render_consult_body(case["metadata"], case["model_responses"], body)
            assert body in out


class TestQuickSynthesisBudget:
    """F2: the fallback's chairman call must not be tier-blind."""

    @pytest.mark.asyncio
    async def test_caller_supplied_timeout_reaches_the_chairman_call(self):
        responses = {"openai/gpt-5.6-sol": {"status": "ok", "response": "a"}}
        with patch("llm_council.council_stages.query_model", new=AsyncMock()) as mock:
            mock.return_value = {"content": "synth", "usage": {}}
            await quick_synthesis("q", responses, timeout=90.0)
        assert mock.await_args.kwargs["timeout"] == 90.0

    @pytest.mark.asyncio
    async def test_chairman_failure_reports_the_source_model_it_fell_back_to(self):
        """The caller cannot label the output honestly without knowing that the
        chairman failed and whose raw text this is."""
        responses = {
            "openai/gpt-5.6-sol": {"status": "ok", "response": "first"},
            "google/gemini-3.1-pro-preview": {"status": "ok", "response": "second"},
        }
        outcome: Dict[str, Any] = {}
        with patch("llm_council.council_stages.query_model", new=AsyncMock(return_value=None)):
            text, _ = await quick_synthesis("q", responses, outcome=outcome)
        assert outcome["chairman"] == "failed"
        assert outcome["source_model"] == "openai/gpt-5.6-sol"
        assert "first" in text

    @pytest.mark.asyncio
    async def test_successful_chairman_reports_ok(self):
        responses = {"openai/gpt-5.6-sol": {"status": "ok", "response": "a"}}
        outcome: Dict[str, Any] = {}
        with patch(
            "llm_council.council_stages.query_model",
            new=AsyncMock(return_value={"content": "synth", "usage": {}}),
        ):
            await quick_synthesis("q", responses, outcome=outcome)
        assert outcome["chairman"] == "ok"

    def test_call_sites_pass_an_explicit_timeout(self):
        """#648's lesson: the defect class here is an omitted kwarg that reads as
        correct code, so pin the call sites rather than the default."""
        source = Path("src/llm_council/council.py").read_text()
        calls = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "quick_synthesis"
        ]
        assert calls, "expected quick_synthesis to be called in council.py"
        for call in calls:
            kwargs = {kw.arg for kw in call.keywords}
            assert "timeout" in kwargs, (
                f"quick_synthesis call at council.py:{call.lineno} omits timeout — "
                "it would silently run at the module default, not the tier budget"
            )


class TestNoArbitraryPickCalledBest:
    """F3: the fallback picks the first survivor in dict order, not the best."""

    def test_source_module_does_not_call_an_arbitrary_pick_best(self):
        tree = ast.parse(Path("src/llm_council/council_stages.py").read_text())
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert "best_response" not in names, (
            "the fallback selects list(successful.values())[0] — first by config "
            "order, with no quality signal (stage 2 never ran on this path). "
            "Naming it 'best' misrepresents an arbitrary pick, and the survivor "
            "set is already biased toward the faster, weaker members."
        )


async def _consult(metadata: Dict[str, Any], model_responses: Dict[str, Any], **kwargs):
    from llm_council.mcp_server import consult_council

    result = {
        "synthesis": "A confident, well-structured answer.",
        "model_responses": model_responses,
        "metadata": metadata,
    }
    with patch(
        "llm_council.mcp_server.run_council_with_fallback",
        new=AsyncMock(return_value=result),
    ):
        return await consult_council("q", **kwargs)


class TestConsultSurface:
    """The rendering fixes have to reach the tool the user actually calls."""

    @pytest.mark.asyncio
    async def test_reported_run_no_longer_claims_a_chairman_synthesis(self):
        out = await _consult(REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"])
        assert CHAIRMAN_HEADING not in out

    @pytest.mark.asyncio
    async def test_reported_run_discloses_before_it_asserts(self):
        out = await _consult(REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"])
        assert out.index("2 of 4") < out.index("A confident, well-structured answer.")

    @pytest.mark.asyncio
    async def test_complete_run_output_is_unchanged_in_substance(self):
        out = await _consult(COMPLETE["metadata"], COMPLETE["model_responses"])
        assert out.startswith(CHAIRMAN_HEADING)

    @pytest.mark.asyncio
    async def test_caller_can_branch_without_parsing_prose(self):
        out = await _consult(REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"])
        payload = json.loads(re.search(r"```json\n(.*?)\n```", out, re.S).group(1))
        assert payload["status"] == "partial"
        assert payload["peer_review"] is False


class TestDissentIsNotSilentlyDropped:
    """F4: council.py stores dissent in metadata for SYNTHESIS mode; the MCP
    surface only ever rendered it inside the ADR-025b verdict block, so
    include_dissent=true was a no-op in the DEFAULT verdict_type."""

    @pytest.mark.asyncio
    async def test_synthesis_mode_renders_extracted_dissent(self):
        metadata = {**COMPLETE["metadata"], "dissent": "gemini ranked C last on grounds of X."}
        out = await _consult(metadata, COMPLETE["model_responses"], include_dissent=True)
        assert "gemini ranked C last on grounds of X." in out

    @pytest.mark.asyncio
    async def test_absent_dissent_is_explained_rather_than_omitted(self):
        out = await _consult(
            COMPLETE["metadata"], COMPLETE["model_responses"], include_dissent=True
        )
        assert "dissent" in out.lower()

    @pytest.mark.asyncio
    async def test_absence_names_peer_review_when_stage_2_never_ran(self):
        out = await _consult(
            REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"], include_dissent=True
        )
        section = out.lower()
        assert "dissent" in section and "peer review" in section

    @pytest.mark.asyncio
    async def test_no_dissent_section_when_not_requested(self):
        out = await _consult(COMPLETE["metadata"], COMPLETE["model_responses"])
        assert "dissent" not in out.lower()


class TestHealthCheckHonesty:
    """F5: `ready` must predict the thing a caller is about to spend money on.

    The reporter's ask was "default deep=true, **or at minimum** make
    `ready: true` conditional on the chairman being reachable". Both halves
    require a chairman call — there is no way to make `ready` chairman-
    conditional without probing it — so the minimum and the maximum are the
    same change. `ready_scope` alone (rev 1 of this fix) only *labelled* the
    gap; it did not close it.
    """

    @staticmethod
    def _probe(chairman_status="ok", lite_status="ok"):
        """Distinguish the lite probe from the chairman probe by model id."""
        from llm_council.openrouter import STATUS_OK

        from llm_council.mcp_server import DEFAULT_HEALTH_CHECK_MODEL

        calls = []

        async def fake(model, messages, **kwargs):
            calls.append(model)
            wanted = lite_status if model == DEFAULT_HEALTH_CHECK_MODEL else chairman_status
            if wanted == "ok":
                return {"status": STATUS_OK, "latency_ms": 10}
            return {"status": wanted, "error": f"{wanted} detail", "latency_ms": 10}

        return fake, calls

    @pytest.mark.asyncio
    async def test_chairman_is_probed_by_default(self):
        from llm_council.mcp_server import council_health_check

        fake, calls = self._probe()
        with (
            patch("llm_council.mcp_server._get_openrouter_api_key", return_value="k"),
            patch("llm_council.mcp_server.query_model_with_status", new=fake),
        ):
            data = json.loads(await council_health_check())

        assert data["ready"] is True
        assert data["ready_scope"] == "chairman_probed"
        assert "chairman_connectivity" in data
        assert any("opus" in c or c != calls[0] for c in calls[1:]), (
            f"expected a second, chairman probe; models called were {calls!r}"
        )

    @pytest.mark.asyncio
    async def test_unreachable_chairman_makes_ready_false_by_default(self):
        """The 2026-07-16 scenario: API up, chairman down, ready said true."""
        from llm_council.mcp_server import council_health_check

        fake, _ = self._probe(chairman_status="timeout")
        with (
            patch("llm_council.mcp_server._get_openrouter_api_key", return_value="k"),
            patch("llm_council.mcp_server.query_model_with_status", new=fake),
        ):
            data = json.loads(await council_health_check())

        assert data["ready"] is False
        assert "chairman" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_opting_out_declares_the_narrower_scope(self):
        from llm_council.mcp_server import council_health_check

        fake, calls = self._probe()
        with (
            patch("llm_council.mcp_server._get_openrouter_api_key", return_value="k"),
            patch("llm_council.mcp_server.query_model_with_status", new=fake),
        ):
            data = json.loads(await council_health_check(deep=False))

        assert data["ready_scope"] == "connectivity_only"
        assert len(calls) == 1, f"deep=False must not spend a chairman call; got {calls!r}"

    @pytest.mark.asyncio
    async def test_dead_api_does_not_spend_a_chairman_call(self):
        """If connectivity already failed, the chairman probe cannot add
        information — and billing for it during an outage is the wrong move."""
        from llm_council.mcp_server import council_health_check

        fake, calls = self._probe(lite_status="auth_error")
        with (
            patch("llm_council.mcp_server._get_openrouter_api_key", return_value="k"),
            patch("llm_council.mcp_server.query_model_with_status", new=fake),
        ):
            data = json.loads(await council_health_check())

        assert data["ready"] is False
        assert len(calls) == 1, f"expected no chairman probe after a dead lite probe; {calls!r}"
        assert "connectivity issue" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_estimates_come_from_the_tier_budget_not_prose(self):
        """F6: health advertised '~60-90 seconds' for high while the same repo
        configures tiers.pools.high.timeout_seconds: 180."""
        from llm_council.mcp_server import _get_tier_timeout, council_health_check
        from llm_council.openrouter import STATUS_OK

        with (
            patch("llm_council.mcp_server._get_openrouter_api_key", return_value="k"),
            patch(
                "llm_council.mcp_server.query_model_with_status",
                new=AsyncMock(return_value={"status": STATUS_OK, "latency_ms": 10}),
            ),
        ):
            data = json.loads(await council_health_check())

        for tier in ("quick", "balanced", "high", "reasoning"):
            budget = int(_get_tier_timeout(tier)["total"])
            assert str(budget) in data["estimated_duration"][tier], (
                f"{tier} estimate {data['estimated_duration'][tier]!r} does not "
                f"mention its configured {budget}s budget"
            )


class TestOnPartial:
    """The reporter's fourth suggestion, and the one that gives a caller a
    choice rather than a disclosure:

    > for `high` tier, a caller who asked for a full council may prefer an
    > error to a confident single opinion. An `on_partial: "error" |
    > "synthesise" | "return_raw"` argument would let the caller choose.

    Honest labelling (the rest of this file) helps a human reading the output.
    It does not help an automated caller that will act on the text regardless.
    """

    @pytest.mark.asyncio
    async def test_default_is_todays_behaviour(self):
        out = await _consult(REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"])
        explicit = await _consult(
            REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"], on_partial="synthesise"
        )
        assert out == explicit

    @pytest.mark.asyncio
    async def test_error_refuses_to_answer_a_partial_run(self):
        out = await _consult(
            REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"], on_partial="error"
        )
        payload = json.loads(out)
        assert payload["error"] == "council_incomplete"
        assert payload["status"] == "partial"
        assert payload["models_responded"] == 2
        assert payload["models_requested"] == 4
        assert payload["peer_review"] is False
        # The content must NOT be smuggled through under an error banner.
        assert "A confident, well-structured answer." not in out

    @pytest.mark.asyncio
    async def test_error_names_which_models_failed_and_why(self):
        out = await _consult(
            REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"], on_partial="error"
        )
        failed = {e["model"]: e["status"] for e in json.loads(out)["failed_models"]}
        assert failed == {
            "anthropic/claude-opus-5": "timeout",
            "deepseek/deepseek-v4-pro-0813": "timeout",
        }

    @pytest.mark.asyncio
    async def test_error_does_not_fire_on_a_complete_run(self):
        out = await _consult(
            COMPLETE["metadata"], COMPLETE["model_responses"], on_partial="error"
        )
        assert out.startswith(CHAIRMAN_HEADING)

    @pytest.mark.asyncio
    async def test_return_raw_gives_the_responses_without_a_synthesis_gloss(self):
        responses = {
            "openai/gpt-5.6-sol": {"status": "ok", "response": "sol's actual take"},
            "anthropic/claude-opus-5": {"status": "timeout"},
            "google/gemini-3.1-pro-preview": {"status": "ok", "response": "gemini's actual take"},
            "deepseek/deepseek-v4-pro-0813": {"status": "timeout"},
        }
        out = await _consult(
            REPORTED_RUN["metadata"], responses, on_partial="return_raw"
        )
        assert "sol's actual take" in out
        assert "gemini's actual take" in out
        # No chairman voice over the top of them.
        assert CHAIRMAN_HEADING not in out
        assert "A confident, well-structured answer." not in out

    @pytest.mark.asyncio
    async def test_return_raw_attributes_each_response_to_its_model(self):
        responses = {
            "openai/gpt-5.6-sol": {"status": "ok", "response": "first take"},
            "anthropic/claude-opus-5": {"status": "timeout"},
        }
        out = await _consult(REPORTED_RUN["metadata"], responses, on_partial="return_raw")
        assert "openai/gpt-5.6-sol" in out
        assert out.index("openai/gpt-5.6-sol") < out.index("first take")

    @pytest.mark.asyncio
    async def test_unknown_value_is_rejected_not_silently_permissive(self):
        """`confidence` silently falls back to "high" on an unknown value. That
        is exactly wrong here: a caller who typos `on_partial="fail"` while
        intending strictness would silently get the permissive behaviour — the
        failure mode this whole issue is about."""
        out = await _consult(
            COMPLETE["metadata"], COMPLETE["model_responses"], on_partial="fail"
        )
        payload = json.loads(out)
        assert payload["error"] == "invalid_on_partial"
        assert "synthesise" in json.dumps(payload)

    @pytest.mark.asyncio
    async def test_every_mode_still_carries_the_machine_readable_status(self):
        for mode in ("synthesise", "return_raw"):
            out = await _consult(
                REPORTED_RUN["metadata"], REPORTED_RUN["model_responses"], on_partial=mode
            )
            payload = json.loads(re.search(r"```json\n(.*?)\n```", out, re.S).group(1))
            assert payload["status"] == "partial", f"mode {mode} dropped the status block"
