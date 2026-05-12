"""End-to-end tests for ADR-042 evidence injection.

Covers spec §14.4 (golden prompt hash) and §14.6 (HTTP 422 mapping).
"""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from llm_council.verification.api import _build_verification_prompt


GOLDEN_HASHES = Path(__file__).parent / "golden_prompts"


@pytest.mark.asyncio
async def test_evidence_none_prompt_byte_identical():
    """ADR-042 backward-compat invariant: evidence=None produces a prompt that
    matches the pre-ADR-042 baseline byte-for-byte.

    The hash in golden_prompts/evidence_none.sha256 was captured immediately
    after the prompt-builder refactor against a known stub. If this test
    fails, you have unintentionally drifted the prompt template — re-read
    the ADR §11 invariant before regenerating the hash.
    """
    with patch(
        "llm_council.verification.api._fetch_files_for_verification_async",
        new_callable=AsyncMock,
        return_value="FILE_BODY_PLACEHOLDER",
    ):
        prompt, info = await _build_verification_prompt(
            snapshot_id="abc1234",
            target_paths=["src/x.py"],
            rubric_focus="Security",
            evidence=None,
            tier="balanced",
        )

    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    expected = (GOLDEN_HASHES / "evidence_none.sha256").read_text().strip()
    assert digest == expected, (
        "Prompt drift detected. Pre-ADR-042 byte-identity is the backward-compat "
        "invariant. If the drift is intentional, regenerate the golden hash and "
        "document the cause in the commit message.\n\n"
        f"Current prompt:\n{prompt}"
    )
    assert info["kept"] == []
    assert info["warnings"] == []
    assert info["chars_rendered"] == 0
    assert info["chars_submitted"] == 0


@pytest.mark.asyncio
async def test_empty_evidence_list_equals_none():
    """ADR-042 §11: evidence=[] produces the same rendered prompt as evidence=None."""
    with patch(
        "llm_council.verification.api._fetch_files_for_verification_async",
        new_callable=AsyncMock,
        return_value="FILE_BODY_PLACEHOLDER",
    ):
        prompt_none, _ = await _build_verification_prompt(
            snapshot_id="abc1234",
            target_paths=["src/x.py"],
            rubric_focus="Security",
            evidence=None,
            tier="balanced",
        )
        prompt_empty, _ = await _build_verification_prompt(
            snapshot_id="abc1234",
            target_paths=["src/x.py"],
            rubric_focus="Security",
            evidence=[],
            tier="balanced",
        )
    assert prompt_none == prompt_empty


@pytest.mark.asyncio
async def test_evidence_section_inserted_at_correct_position():
    """ADR-042 §6: section appears AFTER focus, BEFORE ## Code to Review."""
    from llm_council.verification.api import EvidenceItem

    with patch(
        "llm_council.verification.api._fetch_files_for_verification_async",
        new_callable=AsyncMock,
        return_value="FILE_BODY_PLACEHOLDER",
    ):
        prompt, _ = await _build_verification_prompt(
            snapshot_id="abc1234",
            target_paths=["src/x.py"],
            rubric_focus="Security",
            evidence=[EvidenceItem(source="t@1", content="MY_EVIDENCE_BODY")],
            tier="balanced",
        )

    focus_pos = prompt.index("**Focus Area**: Security")
    evidence_section_pos = prompt.index("## Pre-computed Evidence")
    evidence_body_pos = prompt.index("MY_EVIDENCE_BODY")
    code_section_pos = prompt.index("## Code to Review")
    file_body_pos = prompt.index("FILE_BODY_PLACEHOLDER")

    assert focus_pos < evidence_section_pos
    assert evidence_section_pos < evidence_body_pos
    assert evidence_body_pos < code_section_pos
    assert code_section_pos < file_body_pos


@pytest.mark.asyncio
async def test_evidence_json_artefact_written(tmp_path):
    """ADR-042 §9.4: evidence.json transcript artefact present when evidence
    was submitted, with the expected structure (kept items, budget metadata,
    ordering rule)."""
    import json
    from unittest.mock import MagicMock

    from llm_council.verification.api import EvidenceItem, VerifyRequest, run_verification
    from llm_council.verification.transcript import TranscriptStore

    # Use a real TranscriptStore in a tmp dir so we can inspect on-disk output.
    store = TranscriptStore(base_path=tmp_path)

    # Mock heavy machinery so we can run the pipeline cheaply.
    with (
        patch(
            "llm_council.verification.api._fetch_files_for_verification_async",
            new_callable=AsyncMock,
            return_value="FILE_BODY",
        ),
        patch(
            "llm_council.verification.api.stage1_collect_responses_with_status",
            new_callable=AsyncMock,
            return_value=([{"model": "m1", "response": "r1"}], {}, {"m1": {"latency_ms": 10}}),
        ),
        patch(
            "llm_council.verification.api.stage2_collect_rankings",
            new_callable=AsyncMock,
            return_value=([{"model": "m1", "ranking": "ok", "parsed_ranking": []}], {}, {}),
        ),
        patch(
            "llm_council.verification.api.stage3_synthesize_final",
            new_callable=AsyncMock,
            return_value=(
                {"synthesis": '{"verdict":"approved","confidence":0.9,"rationale":"ok"}\n'},
                {},
                None,
            ),
        ),
        patch("llm_council.verification.api.calculate_aggregate_rankings", return_value=[]),
        patch(
            "llm_council.verification.api.build_verification_result",
            return_value={
                "verdict": "pass",
                "confidence": 0.9,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "ok",
            },
        ),
        patch("llm_council.verification.api.VerificationContextManager") as mock_ctx,
    ):
        mock_ctx_instance = MagicMock()
        mock_ctx_instance.context_id = "test-ctx"
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ctx_instance)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        request = VerifyRequest(
            snapshot_id="abc1234",
            target_paths=["src/x.py"],
            tier="balanced",
            evidence=[
                EvidenceItem(
                    source="slop@1.0",
                    content="Evidence body here",
                    strength="informational",
                ),
            ],
        )
        result = await run_verification(request, store)

    # Find the verification directory and the evidence.json artefact.
    verification_id = result["verification_id"]
    verification_dirs = list(tmp_path.glob(f"*-{verification_id}"))
    assert len(verification_dirs) == 1
    evidence_json_path = verification_dirs[0] / "evidence.json"
    assert evidence_json_path.exists(), "ADR-042: evidence.json artefact must be written"

    data = json.loads(evidence_json_path.read_text())
    assert data["evidence_present"] is True
    assert data["ordering_rule"] == "strength_then_source_then_id"
    assert data["max_evidence_chars"] == 6000  # balanced * 0.20
    assert len(data["items"]) == 1
    assert data["items"][0]["source"] == "slop@1.0"
    assert data["items"][0]["kept"] is True
    assert data["items"][0]["content"] == "Evidence body here"


@pytest.mark.asyncio
async def test_request_json_carries_evidence_present_flag(tmp_path):
    """ADR-042 §9.5: request.json gains `evidence_present` top-level flag."""
    import json
    from unittest.mock import MagicMock

    from llm_council.verification.api import EvidenceItem, VerifyRequest, run_verification
    from llm_council.verification.transcript import TranscriptStore

    store = TranscriptStore(base_path=tmp_path)

    with (
        patch(
            "llm_council.verification.api._fetch_files_for_verification_async",
            new_callable=AsyncMock,
            return_value="FILE_BODY",
        ),
        patch(
            "llm_council.verification.api.stage1_collect_responses_with_status",
            new_callable=AsyncMock,
            return_value=([{"model": "m1", "response": "r1"}], {}, {}),
        ),
        patch(
            "llm_council.verification.api.stage2_collect_rankings",
            new_callable=AsyncMock,
            return_value=([{"model": "m1", "ranking": "ok", "parsed_ranking": []}], {}, {}),
        ),
        patch(
            "llm_council.verification.api.stage3_synthesize_final",
            new_callable=AsyncMock,
            return_value=({"synthesis": "ok"}, {}, None),
        ),
        patch("llm_council.verification.api.calculate_aggregate_rankings", return_value=[]),
        patch(
            "llm_council.verification.api.build_verification_result",
            return_value={
                "verdict": "pass",
                "confidence": 0.9,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "ok",
            },
        ),
        patch("llm_council.verification.api.VerificationContextManager") as mock_ctx,
    ):
        mock_ctx_instance = MagicMock()
        mock_ctx_instance.context_id = "test-ctx"
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ctx_instance)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        # With evidence:
        req_with = VerifyRequest(
            snapshot_id="abc1234",
            evidence=[EvidenceItem(source="s@1", content="x")],
        )
        result_with = await run_verification(req_with, store)
        dir_with = next(tmp_path.glob(f"*-{result_with['verification_id']}"))
        req_with_json = json.loads((dir_with / "request.json").read_text())
        assert req_with_json["evidence_present"] is True

        # Without evidence:
        req_none = VerifyRequest(snapshot_id="abc1234", evidence=None)
        result_none = await run_verification(req_none, store)
        dir_none = next(tmp_path.glob(f"*-{result_none['verification_id']}"))
        req_none_json = json.loads((dir_none / "request.json").read_text())
        assert req_none_json["evidence_present"] is False


@pytest.fixture
def client():
    """FastAPI test client mounting the verification router (mirrors test_api.py)."""
    from llm_council.http_server import app
    from llm_council.verification.api import router as verify_router

    router_paths = [route.path for route in app.routes]
    if "/v1/council/verify" not in router_paths:
        app.include_router(verify_router, prefix="/v1/council")
    return TestClient(app)


class TestHttp422ForOversizedBlocking:
    """ADR-042 §11.1: oversized blocking evidence → HTTP 422 with structured body."""

    def test_blocking_evidence_too_large_returns_422(self, client):
        # balanced tier budget = 6K; one blocking item is 10K → 422.
        payload = {
            "snapshot_id": "abc1234",
            "tier": "balanced",
            "evidence": [
                {
                    "source": "blk@1",
                    "content": "x" * 10000,
                    "strength": "blocking",
                }
            ],
        }
        response = client.post("/v1/council/verify", json=payload)
        assert response.status_code == 422
        body = response.json()
        assert body["detail"]["error"] == "blocking_evidence_too_large"
        assert body["detail"]["evidence_index"] == 0
        assert body["detail"]["source"] == "blk@1"
        assert body["detail"]["chars"] == 10000
        assert body["detail"]["budget"] == 6000
        assert body["detail"]["tier"] == "balanced"


class TestMcpWrapperEvidenceParameter:
    """ADR-042 §12: MCP wrapper accepts evidence + mirrors HTTP 422 error formatting."""

    @pytest.mark.asyncio
    async def test_mcp_verify_accepts_evidence_parameter(self):
        """Smoke test: MCP verify tool accepts the new `evidence` kwarg without crash."""
        from llm_council.mcp_server import verify

        # The tool is registered via @mcp.tool() decorator; access the underlying
        # function via its FunctionTool fn attribute.
        verify_fn = verify.fn if hasattr(verify, "fn") else verify

        with patch(
            "llm_council.mcp_server.run_verification",
            new_callable=AsyncMock,
            return_value={
                "verification_id": "x",
                "verdict": "pass",
                "confidence": 0.9,
                "exit_code": 0,
                "rubric_scores": {},
                "blocking_issues": [],
                "rationale": "ok",
                "transcript_location": "/tmp/x",
                "partial": False,
                "timeout_fired": False,
                "completed_stages": ["stage1", "stage2", "stage3"],
            },
        ):
            result = await verify_fn(
                snapshot_id="abc1234",
                tier="balanced",
                evidence=[{"source": "s@1", "content": "x"}],
            )
            # Result is a formatted string with raw JSON appended.
            assert "abc1234" in result or "verdict" in result

    @pytest.mark.asyncio
    async def test_mcp_verify_returns_structured_error_for_oversized_blocking(self):
        """ADR-042 §12.2: MCP wrapper catches BlockingEvidenceTooLarge and
        returns a JSON error blob — never raises."""
        import json as json_lib
        from llm_council.mcp_server import verify

        verify_fn = verify.fn if hasattr(verify, "fn") else verify

        result = await verify_fn(
            snapshot_id="abc1234",
            tier="balanced",
            evidence=[
                {
                    "source": "blk@1",
                    "content": "x" * 10000,
                    "strength": "blocking",
                }
            ],
        )
        parsed = json_lib.loads(result)
        assert parsed["error"] == "blocking_evidence_too_large"
        assert parsed["evidence_index"] == 0
        assert parsed["source"] == "blk@1"
        assert parsed["chars"] == 10000
        assert parsed["budget"] == 6000


@pytest.mark.asyncio
async def test_evidence_instructions_added_only_when_evidence_present():
    """ADR-042 §4: anti-rubber-stamping clause only appears when evidence != None/[]."""
    from llm_council.verification.api import EvidenceItem

    with patch(
        "llm_council.verification.api._fetch_files_for_verification_async",
        new_callable=AsyncMock,
        return_value="FILE_BODY_PLACEHOLDER",
    ):
        prompt_none, _ = await _build_verification_prompt(
            snapshot_id="abc1234",
            target_paths=["src/x.py"],
            rubric_focus=None,
            evidence=None,
            tier="balanced",
        )
        prompt_with, _ = await _build_verification_prompt(
            snapshot_id="abc1234",
            target_paths=["src/x.py"],
            rubric_focus=None,
            evidence=[EvidenceItem(source="t@1", content="x")],
            tier="balanced",
        )

    # Anti-rubber-stamping clause keyword (from spec §4 point 1).
    assert "Form your own view from the source code first" not in prompt_none
    assert "Form your own view from the source code first" in prompt_with
