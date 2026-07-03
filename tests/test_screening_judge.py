"""ADR-047 P3: lightweight screening judge, shadow-first (#415).

Invariants: blocking-capable requests are NEVER screened; flag-off is
byte-identical (no screen call at all); every decision is logged with its
scores; active mode short-circuits only on a unanimous pass.
"""

import json

import pytest

from llm_council.verification.screening import (
    ScreenDecision,
    log_decision,
    parse_screen_scores,
    screen_eligibility,
    screen_passes,
    screening_mode,
)


class TestMode:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_SCREENING", raising=False)
        assert screening_mode() == "off"

    def test_unknown_degrades_to_off(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_SCREENING", "banana")
        assert screening_mode() == "off"

    @pytest.mark.parametrize("mode", ["shadow", "active"])
    def test_explicit_modes(self, monkeypatch, mode):
        monkeypatch.setenv("LLM_COUNCIL_SCREENING", mode)
        assert screening_mode() == mode


class TestEligibilityInvariants:
    def test_blocking_evidence_never_screened(self):
        reasons = screen_eligibility(
            content_chars=100,
            target_paths=["src/x.py"],
            rubric_focus=None,
            evidence=[{"strength": "blocking", "content": "must fix"}],
        )
        assert "blocking_evidence" in reasons

    def test_security_focus_never_screened(self):
        reasons = screen_eligibility(
            content_chars=100,
            target_paths=None,
            rubric_focus="Security",
            evidence=None,
        )
        assert "security_focus" in reasons

    def test_large_content_ineligible(self):
        reasons = screen_eligibility(
            content_chars=5001, target_paths=None, rubric_focus=None, evidence=None
        )
        assert any(r.startswith("content_too_large") for r in reasons)

    @pytest.mark.parametrize(
        "path",
        ["src/auth_handler.py", "lib/security_utils.py", "core/crypto.rs", "api/stripe_payment.py"],
    )
    def test_risk_globs_ineligible(self, path):
        reasons = screen_eligibility(
            content_chars=100, target_paths=[path], rubric_focus=None, evidence=None
        )
        assert any(r.startswith("risk_path") for r in reasons)

    def test_small_benign_change_eligible(self):
        assert (
            screen_eligibility(
                content_chars=1000,
                target_paths=["docs/readme.md"],
                rubric_focus=None,
                evidence=[{"strength": "informational", "content": "fyi"}],
            )
            == []
        )


class TestScoring:
    def test_parse_valid_json(self):
        text = 'Here: {"accuracy": 9, "relevance": 10, "completeness": 9.5, "conciseness": 9, "clarity": 10}'
        scores = parse_screen_scores(text)
        assert scores["accuracy"] == 9.0

    def test_incomplete_scores_rejected(self):
        assert parse_screen_scores('{"accuracy": 9}') is None
        assert parse_screen_scores("no json here") is None

    def test_unanimity_rule(self):
        base = {d: 9.0 for d in ("accuracy", "relevance", "completeness", "conciseness", "clarity")}
        assert screen_passes(base) is True
        base["clarity"] = 8.9
        assert screen_passes(base) is False
        assert screen_passes(None) is False


class TestDecisionLog:
    def test_logged_with_scores(self, tmp_path):
        path = tmp_path / "decisions.jsonl"
        decision = ScreenDecision(
            verification_id="v1",
            mode="shadow",
            eligible=True,
            scores={"accuracy": 9.0},
            screen_pass=False,
        )
        log_decision(decision, path)
        row = json.loads(path.read_text().splitlines()[0])
        assert row["verification_id"] == "v1"
        assert row["scores"] == {"accuracy": 9.0}
        assert row["acted"] is False
        assert row["ts"] > 0


class TestWiring:
    def _common_patches(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock, patch

        return patch, AsyncMock, MagicMock

    @pytest.mark.asyncio
    async def test_flag_off_makes_no_screen_call(self, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.verification.api import VerifyRequest, run_verification

        monkeypatch.delenv("LLM_COUNCIL_SCREENING", raising=False)
        request = VerifyRequest(snapshot_id="abc1234", tier="quick")

        async def instant_pipeline(*a, **kw):
            return {"verification_id": "x", "verdict": "pass", "confidence": 0.9,
                    "exit_code": 0, "rubric_scores": {}, "blocking_issues": [],
                    "rationale": "r", "transcript_location": "/tmp/t",
                    "partial": False, "timeout_fired": False,
                    "completed_stages": ["stage1", "stage2", "stage3"]}

        with (
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value=("short prompt", {"kept": [], "warnings": []}),
            ),
            patch(
                "llm_council.verification.api._run_verification_pipeline",
                side_effect=instant_pipeline,
            ),
            patch(
                "llm_council.verification.api.run_screen", new_callable=AsyncMock
            ) as screen,
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)
            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

        screen.assert_not_awaited()  # byte-identical: no screen call at all
        assert "screening" not in result

    @pytest.mark.asyncio
    async def test_shadow_logs_but_never_short_circuits(self, monkeypatch, tmp_path):
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.verification import screening as screening_mod
        from llm_council.verification.api import VerifyRequest, run_verification

        monkeypatch.setenv("LLM_COUNCIL_SCREENING", "shadow")
        monkeypatch.setattr(
            screening_mod, "DEFAULT_DECISIONS_PATH", tmp_path / "d.jsonl"
        )
        # api.py imported log_decision by name; patch where it's used.
        request = VerifyRequest(snapshot_id="abc1234", tier="quick")
        perfect = {d: 10.0 for d in ("accuracy", "relevance", "completeness", "conciseness", "clarity")}

        async def instant_pipeline(*a, **kw):
            return {"verification_id": "x", "verdict": "fail", "confidence": 0.9,
                    "exit_code": 1, "rubric_scores": {}, "blocking_issues": [],
                    "rationale": "council ran", "transcript_location": "/tmp/t",
                    "partial": False, "timeout_fired": False,
                    "completed_stages": ["stage1", "stage2", "stage3"]}

        logged = []
        with (
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value=("short prompt", {"kept": [], "warnings": []}),
            ),
            patch(
                "llm_council.verification.api._run_verification_pipeline",
                side_effect=instant_pipeline,
            ),
            patch(
                "llm_council.verification.api.run_screen",
                new_callable=AsyncMock,
                return_value=perfect,
            ),
            patch(
                "llm_council.verification.api.log_decision",
                side_effect=lambda d, path=None: logged.append(d),
            ),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)
            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

        # Full council result stands even though the screen passed perfectly.
        assert result["verdict"] == "fail"
        assert result["screening"]["screen_pass"] is True
        assert result["screening"]["acted"] is False
        assert len(logged) == 1 and logged[0].screen_pass is True

    @pytest.mark.asyncio
    async def test_active_short_circuits_on_unanimous_pass(self, monkeypatch, tmp_path):
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.verification.api import VerifyRequest, run_verification

        monkeypatch.setenv("LLM_COUNCIL_SCREENING", "active")
        request = VerifyRequest(snapshot_id="abc1234", tier="quick")
        perfect = {d: 9.5 for d in ("accuracy", "relevance", "completeness", "conciseness", "clarity")}

        pipeline = AsyncMock()
        with (
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value=("short prompt", {"kept": [], "warnings": []}),
            ),
            patch(
                "llm_council.verification.api._run_verification_pipeline", pipeline
            ),
            patch(
                "llm_council.verification.api.run_screen",
                new_callable=AsyncMock,
                return_value=perfect,
            ),
            patch("llm_council.verification.api.log_decision"),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)
            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

        pipeline.assert_not_awaited()  # council never ran
        assert result["verdict"] == "pass"
        assert result["exit_code"] == 0
        assert result["screening"]["acted"] is True
        assert "AUDIT NOTE" in result["rationale"]

    @pytest.mark.asyncio
    async def test_active_blocking_capable_always_full_council(self, monkeypatch):
        # THE invariant: blocking evidence => never screened, even active.
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.verification.api import VerifyRequest, run_verification

        monkeypatch.setenv("LLM_COUNCIL_SCREENING", "active")
        request = VerifyRequest(
            snapshot_id="abc1234",
            tier="quick",
            evidence=[
                {
                    "id": "e1",
                    "source": "reviewer",
                    "strength": "blocking",
                    "content": "must address",
                }
            ],
        )

        async def instant_pipeline(*a, **kw):
            return {"verification_id": "x", "verdict": "fail", "confidence": 0.9,
                    "exit_code": 1, "rubric_scores": {}, "blocking_issues": [],
                    "rationale": "council ran", "transcript_location": "/tmp/t",
                    "partial": False, "timeout_fired": False,
                    "completed_stages": ["stage1", "stage2", "stage3"]}

        screen = AsyncMock()
        with (
            patch("llm_council.verification.api.VerificationContextManager") as mock_ctx_mgr,
            patch(
                "llm_council.verification.api._build_verification_prompt",
                new_callable=AsyncMock,
                return_value=("short prompt", {"kept": [], "warnings": []}),
            ),
            patch(
                "llm_council.verification.api._run_verification_pipeline",
                side_effect=instant_pipeline,
            ),
            patch("llm_council.verification.api.run_screen", screen),
            patch("llm_council.verification.api.log_decision"),
        ):
            mock_ctx = MagicMock()
            mock_ctx.context_id = "test-ctx"
            mock_ctx_mgr.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx_mgr.return_value.__exit__ = MagicMock(return_value=False)
            mock_store = MagicMock()
            mock_store.create_verification_directory.return_value = "/tmp/test"

            result = await run_verification(request, mock_store)

        screen.assert_not_awaited()  # ineligible: screen model never called
        assert result["verdict"] == "fail"  # full council verdict stands
        assert result["screening"]["eligible"] is False
        assert "blocking_evidence" in result["screening"]["reasons"]
