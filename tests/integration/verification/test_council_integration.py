"""
Integration tests for council deliberation in verification per ADR-034.

TDD Red Phase: These tests verify that run_verification() actually
calls council stages instead of returning hardcoded values.

Unlike test_api.py which mocks run_verification(), these tests
call the actual function to verify council integration works.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from llm_council.verification.api import VerifyRequest, run_verification
from llm_council.verification.transcript import TranscriptStore


class TestCouncilDeliberationIntegration:
    """Tests that verify run_verification() calls council stages."""

    @pytest.fixture
    def temp_transcript_dir(self, tmp_path: Path) -> Path:
        """Create temporary transcript directory."""
        transcript_dir = tmp_path / ".council" / "logs"
        transcript_dir.mkdir(parents=True)
        return transcript_dir

    @pytest.fixture
    def transcript_store(self, temp_transcript_dir: Path) -> TranscriptStore:
        """Create transcript store for testing."""
        return TranscriptStore(base_path=temp_transcript_dir)

    @pytest.fixture
    def valid_request(self) -> VerifyRequest:
        """Create valid verification request."""
        return VerifyRequest(
            snapshot_id="abc1234def5678",
            target_paths=["src/"],
            rubric_focus="Security",
            confidence_threshold=0.7,
        )

    @pytest.fixture
    def mock_stage1_result(self) -> list:
        """Mock Stage 1 responses from council models."""
        return [
            {
                "model": "openai/gpt-4o",
                "response": "The code follows security best practices. "
                "Input validation is present and SQL injection is prevented.",
            },
            {
                "model": "anthropic/claude-3.5-sonnet",
                "response": "Security review: The implementation correctly "
                "sanitizes user input and uses parameterized queries.",
            },
            {
                "model": "google/gemini-pro-1.5",
                "response": "This code appears secure. Authentication is "
                "handled properly with JWT tokens.",
            },
        ]

    @pytest.fixture
    def mock_stage2_result(self) -> tuple:
        """Mock Stage 2 rankings with rubric scores."""
        rankings = [
            {
                "reviewer": "openai/gpt-4o",
                "evaluation": "Response B provides the most comprehensive analysis.",
                "parsed_ranking": ["Response B", "Response A", "Response C"],
                "rubric_scores": {
                    "accuracy": 9.0,
                    "relevance": 8.5,
                    "completeness": 8.0,
                    "conciseness": 7.5,
                    "clarity": 8.5,
                },
            },
            {
                "reviewer": "anthropic/claude-3.5-sonnet",
                "evaluation": "Response A offers clear security assessment.",
                "parsed_ranking": ["Response A", "Response B", "Response C"],
                "rubric_scores": {
                    "accuracy": 8.5,
                    "relevance": 9.0,
                    "completeness": 8.5,
                    "conciseness": 8.0,
                    "clarity": 9.0,
                },
            },
        ]
        label_to_model = {
            "Response A": {"model": "openai/gpt-4o", "display_index": 0},
            "Response B": {"model": "anthropic/claude-3.5-sonnet", "display_index": 1},
            "Response C": {"model": "google/gemini-pro-1.5", "display_index": 2},
        }
        usage = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
        return rankings, label_to_model, usage

    @pytest.fixture
    def mock_stage3_result(self) -> tuple:
        """Mock Stage 3 synthesis with verdict."""
        synthesis = {
            "model": "anthropic/claude-3.5-sonnet",
            "response": "VERDICT: APPROVED\n\nBased on council consensus, "
            "the code meets security requirements. All reviewers agree that "
            "input validation and authentication are properly implemented.",
        }
        usage = {"prompt_tokens": 800, "completion_tokens": 400, "total_tokens": 1200}
        verdict_result = None  # VerdictResult for BINARY mode
        return synthesis, usage, verdict_result

    @pytest.fixture
    def mock_aggregate_rankings(self) -> list:
        """Mock aggregate rankings result."""
        return [
            {"model": "anthropic/claude-3.5-sonnet", "borda_score": 0.9, "rank": 1},
            {"model": "openai/gpt-4o", "borda_score": 0.7, "rank": 2},
            {"model": "google/gemini-pro-1.5", "borda_score": 0.5, "rank": 3},
        ]

    @pytest.mark.asyncio
    async def test_calls_stage1_collect_responses(
        self,
        valid_request: VerifyRequest,
        transcript_store: TranscriptStore,
        mock_stage1_result: list,
        mock_stage2_result: tuple,
        mock_stage3_result: tuple,
        mock_aggregate_rankings: list,
    ):
        """run_verification() should call stage1_collect_responses()."""
        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = (mock_stage1_result, {"total_tokens": 1000})
            mock_stage2.return_value = mock_stage2_result
            mock_stage3.return_value = mock_stage3_result
            mock_agg.return_value = mock_aggregate_rankings

            await run_verification(valid_request, transcript_store)

            # Stage 1 should be called with verification prompt
            mock_stage1.assert_called_once()
            call_args = mock_stage1.call_args
            assert call_args is not None
            # First positional arg should be the verification query
            query = call_args[0][0] if call_args[0] else call_args[1].get("user_query")
            assert query is not None

    @pytest.mark.asyncio
    async def test_calls_stage2_collect_rankings(
        self,
        valid_request: VerifyRequest,
        transcript_store: TranscriptStore,
        mock_stage1_result: list,
        mock_stage2_result: tuple,
        mock_stage3_result: tuple,
        mock_aggregate_rankings: list,
    ):
        """run_verification() should call stage2_collect_rankings()."""
        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = (mock_stage1_result, {"total_tokens": 1000})
            mock_stage2.return_value = mock_stage2_result
            mock_stage3.return_value = mock_stage3_result
            mock_agg.return_value = mock_aggregate_rankings

            await run_verification(valid_request, transcript_store)

            # Stage 2 should be called with stage1 results
            mock_stage2.assert_called_once()
            call_args = mock_stage2.call_args
            assert call_args is not None
            # Should receive stage1 results
            stage1_input = (
                call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("stage1_results")
            )
            assert stage1_input == mock_stage1_result

    @pytest.mark.asyncio
    async def test_calls_stage3_synthesize_final(
        self,
        valid_request: VerifyRequest,
        transcript_store: TranscriptStore,
        mock_stage1_result: list,
        mock_stage2_result: tuple,
        mock_stage3_result: tuple,
        mock_aggregate_rankings: list,
    ):
        """run_verification() should call stage3_synthesize_final()."""
        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = (mock_stage1_result, {"total_tokens": 1000})
            mock_stage2.return_value = mock_stage2_result
            mock_stage3.return_value = mock_stage3_result
            mock_agg.return_value = mock_aggregate_rankings

            await run_verification(valid_request, transcript_store)

            # Stage 3 should be called
            mock_stage3.assert_called_once()


class TestTranscriptPersistence:
    """Tests that verify all stages are written to transcript."""

    @pytest.fixture
    def temp_transcript_dir(self, tmp_path: Path) -> Path:
        """Create temporary transcript directory."""
        transcript_dir = tmp_path / ".council" / "logs"
        transcript_dir.mkdir(parents=True)
        return transcript_dir

    @pytest.fixture
    def transcript_store(self, temp_transcript_dir: Path) -> TranscriptStore:
        """Create transcript store for testing."""
        return TranscriptStore(base_path=temp_transcript_dir)

    @pytest.fixture
    def valid_request(self) -> VerifyRequest:
        """Create valid verification request."""
        return VerifyRequest(
            snapshot_id="abc1234def5678",
            target_paths=["src/"],
            rubric_focus="Security",
            confidence_threshold=0.7,
        )

    @pytest.fixture
    def mock_council_responses(self):
        """Mock all council stage responses."""
        stage1 = [
            {"model": "openai/gpt-4o", "response": "Security review passed."},
            {"model": "anthropic/claude-3.5-sonnet", "response": "Code is secure."},
        ]
        stage2_rankings = [
            {
                "reviewer": "openai/gpt-4o",
                "evaluation": "Both responses are accurate.",
                "parsed_ranking": ["Response A", "Response B"],
                "rubric_scores": {"accuracy": 8.5, "relevance": 8.0},
            },
        ]
        stage2_label_map = {
            "Response A": {"model": "openai/gpt-4o", "display_index": 0},
            "Response B": {"model": "anthropic/claude-3.5-sonnet", "display_index": 1},
        }
        stage3 = {
            "model": "anthropic/claude-3.5-sonnet",
            "response": "VERDICT: APPROVED. Code meets requirements.",
        }
        aggregate = [
            {"model": "openai/gpt-4o", "borda_score": 0.8, "rank": 1},
            {"model": "anthropic/claude-3.5-sonnet", "borda_score": 0.6, "rank": 2},
        ]
        return {
            "stage1": (stage1, {"total_tokens": 500}),
            "stage2": (stage2_rankings, stage2_label_map, {"total_tokens": 800}),
            "stage3": (stage3, {"total_tokens": 300}, None),
            "aggregate": aggregate,
        }

    @pytest.mark.asyncio
    async def test_writes_stage1_json_to_transcript(
        self,
        valid_request: VerifyRequest,
        transcript_store: TranscriptStore,
        temp_transcript_dir: Path,
        mock_council_responses: dict,
    ):
        """run_verification() should write stage1.json to transcript."""
        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = mock_council_responses["stage1"]
            mock_stage2.return_value = mock_council_responses["stage2"]
            mock_stage3.return_value = mock_council_responses["stage3"]
            mock_agg.return_value = mock_council_responses["aggregate"]

            result = await run_verification(valid_request, transcript_store)

            # Check that stage1.json was written
            verification_id = result["verification_id"]
            transcript_dir = transcript_store._find_verification_dir(verification_id)
            stage1_file = transcript_dir / "stage1.json"

            assert stage1_file.exists(), "stage1.json should be written to transcript"

    @pytest.mark.asyncio
    async def test_writes_stage2_json_to_transcript(
        self,
        valid_request: VerifyRequest,
        transcript_store: TranscriptStore,
        temp_transcript_dir: Path,
        mock_council_responses: dict,
    ):
        """run_verification() should write stage2.json to transcript."""
        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = mock_council_responses["stage1"]
            mock_stage2.return_value = mock_council_responses["stage2"]
            mock_stage3.return_value = mock_council_responses["stage3"]
            mock_agg.return_value = mock_council_responses["aggregate"]

            result = await run_verification(valid_request, transcript_store)

            # Check that stage2.json was written
            verification_id = result["verification_id"]
            transcript_dir = transcript_store._find_verification_dir(verification_id)
            stage2_file = transcript_dir / "stage2.json"

            assert stage2_file.exists(), "stage2.json should be written to transcript"

    @pytest.mark.asyncio
    async def test_writes_stage3_json_to_transcript(
        self,
        valid_request: VerifyRequest,
        transcript_store: TranscriptStore,
        temp_transcript_dir: Path,
        mock_council_responses: dict,
    ):
        """run_verification() should write stage3.json to transcript."""
        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = mock_council_responses["stage1"]
            mock_stage2.return_value = mock_council_responses["stage2"]
            mock_stage3.return_value = mock_council_responses["stage3"]
            mock_agg.return_value = mock_council_responses["aggregate"]

            result = await run_verification(valid_request, transcript_store)

            # Check that stage3.json was written
            verification_id = result["verification_id"]
            transcript_dir = transcript_store._find_verification_dir(verification_id)
            stage3_file = transcript_dir / "stage3.json"

            assert stage3_file.exists(), "stage3.json should be written to transcript"


class TestDynamicScoreExtraction:
    """Tests that verify rubric scores are extracted from council, not hardcoded."""

    @pytest.fixture
    def temp_transcript_dir(self, tmp_path: Path) -> Path:
        """Create temporary transcript directory."""
        transcript_dir = tmp_path / ".council" / "logs"
        transcript_dir.mkdir(parents=True)
        return transcript_dir

    @pytest.fixture
    def transcript_store(self, temp_transcript_dir: Path) -> TranscriptStore:
        """Create transcript store for testing."""
        return TranscriptStore(base_path=temp_transcript_dir)

    @pytest.fixture
    def valid_request(self) -> VerifyRequest:
        """Create valid verification request."""
        return VerifyRequest(
            snapshot_id="abc1234def5678",
            target_paths=["src/"],
            rubric_focus="Security",
            confidence_threshold=0.7,
        )

    @pytest.mark.asyncio
    async def test_rubric_scores_extracted_from_stage2(
        self,
        valid_request: VerifyRequest,
        transcript_store: TranscriptStore,
    ):
        """Rubric scores should be extracted from Stage 2, not hardcoded."""
        # Distinct scores that are NOT the hardcoded values
        expected_scores = {
            "accuracy": 7.2,  # Not 8.5
            "relevance": 6.8,  # Not 8.0
            "completeness": 9.1,  # Not 7.5
            "conciseness": 5.5,  # Not 8.0
            "clarity": 8.3,  # Not 8.5
        }

        stage2_rankings = [
            {
                "reviewer": "openai/gpt-4o",
                "rubric_scores": expected_scores,
            },
        ]

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = (
                [{"model": "openai/gpt-4o", "response": "Looks good."}],
                {"total_tokens": 100},
            )
            mock_stage2.return_value = (
                stage2_rankings,
                {"Response A": {"model": "openai/gpt-4o", "display_index": 0}},
                {"total_tokens": 200},
            )
            mock_stage3.return_value = (
                {"model": "anthropic/claude-3.5-sonnet", "response": "APPROVED"},
                {"total_tokens": 100},
                None,
            )
            mock_agg.return_value = [{"model": "openai/gpt-4o", "borda_score": 0.9, "rank": 1}]

            result = await run_verification(valid_request, transcript_store)

            # Verify scores come from stage2, not hardcoded
            rubric_scores = result["rubric_scores"]
            assert rubric_scores["accuracy"] == expected_scores["accuracy"], (
                f"Expected accuracy {expected_scores['accuracy']}, "
                f"got {rubric_scores['accuracy']} (hardcoded value is 8.5)"
            )
            assert rubric_scores["completeness"] == expected_scores["completeness"], (
                f"Expected completeness {expected_scores['completeness']}, "
                f"got {rubric_scores['completeness']} (hardcoded value is 7.5)"
            )

    @pytest.mark.asyncio
    async def test_confidence_not_hardcoded(
        self,
        valid_request: VerifyRequest,
        transcript_store: TranscriptStore,
    ):
        """Confidence should be calculated from council agreement, not hardcoded."""
        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = (
                [{"model": "openai/gpt-4o", "response": "Review complete."}],
                {"total_tokens": 100},
            )
            mock_stage2.return_value = (
                [{"reviewer": "openai/gpt-4o", "rubric_scores": {"accuracy": 6.0}}],
                {"Response A": {"model": "openai/gpt-4o", "display_index": 0}},
                {"total_tokens": 200},
            )
            mock_stage3.return_value = (
                {"model": "anthropic/claude-3.5-sonnet", "response": "APPROVED"},
                {"total_tokens": 100},
                None,
            )
            mock_agg.return_value = [{"model": "openai/gpt-4o", "borda_score": 0.8, "rank": 1}]

            result = await run_verification(valid_request, transcript_store)

            # Confidence should NOT be exactly 0.85 (the hardcoded value)
            # It should be calculated based on council agreement
            confidence = result["confidence"]
            assert confidence != 0.85, (
                f"Confidence is exactly 0.85, which suggests hardcoded value. "
                f"Should be calculated from council agreement."
            )


class TestVerdictExtraction:
    """Tests that verify verdict is extracted from council synthesis."""

    @pytest.fixture
    def temp_transcript_dir(self, tmp_path: Path) -> Path:
        """Create temporary transcript directory."""
        transcript_dir = tmp_path / ".council" / "logs"
        transcript_dir.mkdir(parents=True)
        return transcript_dir

    @pytest.fixture
    def transcript_store(self, temp_transcript_dir: Path) -> TranscriptStore:
        """Create transcript store for testing."""
        return TranscriptStore(base_path=temp_transcript_dir)

    @pytest.mark.asyncio
    async def test_verdict_extracted_from_synthesis_approved(
        self,
        transcript_store: TranscriptStore,
    ):
        """Verdict 'pass' should be extracted when synthesis says APPROVED."""
        request = VerifyRequest(
            snapshot_id="abc1234def5678",
            confidence_threshold=0.7,
        )

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = (
                [{"model": "openai/gpt-4o", "response": "OK"}],
                {"total_tokens": 100},
            )
            mock_stage2.return_value = (
                [{"reviewer": "openai/gpt-4o", "rubric_scores": {"accuracy": 9.0}}],
                {"Response A": {"model": "openai/gpt-4o", "display_index": 0}},
                {"total_tokens": 200},
            )
            mock_stage3.return_value = (
                {
                    "model": "anthropic/claude-3.5-sonnet",
                    "response": "VERDICT: APPROVED\n\nThe code meets all requirements.",
                },
                {"total_tokens": 100},
                None,
            )
            mock_agg.return_value = [{"model": "openai/gpt-4o", "borda_score": 0.9, "rank": 1}]

            result = await run_verification(request, transcript_store)

            assert result["verdict"] == "pass"
            assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_verdict_extracted_from_synthesis_rejected(
        self,
        transcript_store: TranscriptStore,
    ):
        """Verdict 'fail' should be extracted when synthesis says REJECTED."""
        request = VerifyRequest(
            snapshot_id="abc1234def5678",
            confidence_threshold=0.7,
        )

        with (
            patch(
                "llm_council.verification.api.stage1_collect_responses", new_callable=AsyncMock
            ) as mock_stage1,
            patch(
                "llm_council.verification.api.stage2_collect_rankings", new_callable=AsyncMock
            ) as mock_stage2,
            patch(
                "llm_council.verification.api.stage3_synthesize_final", new_callable=AsyncMock
            ) as mock_stage3,
            patch("llm_council.verification.api.calculate_aggregate_rankings") as mock_agg,
        ):
            mock_stage1.return_value = (
                [{"model": "openai/gpt-4o", "response": "Security issues found."}],
                {"total_tokens": 100},
            )
            mock_stage2.return_value = (
                [{"reviewer": "openai/gpt-4o", "rubric_scores": {"accuracy": 3.0}}],
                {"Response A": {"model": "openai/gpt-4o", "display_index": 0}},
                {"total_tokens": 200},
            )
            mock_stage3.return_value = (
                {
                    "model": "anthropic/claude-3.5-sonnet",
                    "response": "VERDICT: REJECTED\n\nCritical security vulnerabilities.",
                },
                {"total_tokens": 100},
                None,
            )
            mock_agg.return_value = [{"model": "openai/gpt-4o", "borda_score": 0.3, "rank": 1}]

            result = await run_verification(request, transcript_store)

            assert result["verdict"] == "fail"
            assert result["exit_code"] == 1
