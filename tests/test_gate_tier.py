"""#445: gate --tier passthrough (epic #443)."""

from unittest.mock import AsyncMock, MagicMock, patch

from llm_council.cli import run_gate


class TestGateTier:
    def test_tier_reaches_verify_request(self):
        captured = {}

        async def fake_run_verification(request, store):
            captured["tier"] = request.tier
            return {"verdict": "pass", "confidence": 0.9, "exit_code": 0,
                    "rubric_scores": {}, "blocking_issues": [], "rationale": "r",
                    "transcript_location": "/tmp/t"}

        with (
            patch("llm_council.verification.api.run_verification", fake_run_verification),
            patch("llm_council.verification.transcript.create_transcript_store", MagicMock()),
        ):
            code = run_gate(snapshot="abc1234", tier="quick")
        assert captured["tier"] == "quick"
        assert code == 0

    def test_default_tier_balanced(self):
        captured = {}

        async def fake_run_verification(request, store):
            captured["tier"] = request.tier
            return {"verdict": "unclear", "confidence": 0.4, "exit_code": 2,
                    "unclear_reason": "low_confidence",
                    "rubric_scores": {}, "blocking_issues": [], "rationale": "r",
                    "transcript_location": "/tmp/t"}

        with (
            patch("llm_council.verification.api.run_verification", fake_run_verification),
            patch("llm_council.verification.transcript.create_transcript_store", MagicMock()),
        ):
            code = run_gate(snapshot="abc1234")
        assert captured["tier"] == "balanced"
        assert code == 2

    def test_text_output_surfaces_unclear_reason(self, capsys):
        async def fake_run_verification(request, store):
            return {"verdict": "unclear", "confidence": 0.4, "exit_code": 2,
                    "unclear_reason": "infra_failure",
                    "rubric_scores": {}, "blocking_issues": [], "rationale": "r",
                    "transcript_location": "/tmp/t"}

        with (
            patch("llm_council.verification.api.run_verification", fake_run_verification),
            patch("llm_council.verification.transcript.create_transcript_store", MagicMock()),
        ):
            run_gate(snapshot="abc1234")
        out = capsys.readouterr().out
        assert "infra_failure" in out
