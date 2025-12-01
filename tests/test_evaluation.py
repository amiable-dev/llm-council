"""Tests for evaluation harness."""

import pytest
import json
import tempfile
from pathlib import Path

from llm_council.evaluation import (
    evaluate_response,
    load_test_dataset,
    calculate_aggregate_stats,
    print_benchmark_report,
    EvaluationCriteria,
    BenchmarkQuestion,
    BenchmarkResult,
    ResponseScore,
    SAMPLE_BENCHMARK,
    create_sample_benchmark_file,
)


class TestEvaluateResponse:
    """Tests for the evaluate_response function."""

    def test_full_coverage(self):
        """Test response that meets all criteria."""
        criteria = [
            EvaluationCriteria(
                description="Mentions REST",
                keywords=["REST", "restful"],
            ),
            EvaluationCriteria(
                description="Mentions GraphQL",
                keywords=["GraphQL", "graph ql"],
            ),
        ]

        response = "REST is a traditional API architecture while GraphQL provides flexible queries."
        score = evaluate_response(response, criteria)

        assert score.criteria_met == 2
        assert score.criteria_total == 2
        assert score.coverage_score == 1.0

    def test_partial_coverage(self):
        """Test response that meets some criteria."""
        criteria = [
            EvaluationCriteria(
                description="Mentions caching",
                keywords=["cache", "caching"],
            ),
            EvaluationCriteria(
                description="Mentions scaling",
                keywords=["scale", "scaling", "horizontal"],
            ),
            EvaluationCriteria(
                description="Mentions security",
                keywords=["security", "authentication", "authorization"],
            ),
        ]

        response = "Caching is important for performance. You should also consider security."
        score = evaluate_response(response, criteria)

        assert score.criteria_met == 2  # caching and security
        assert score.criteria_total == 3
        assert abs(score.coverage_score - 0.667) < 0.01

    def test_no_coverage(self):
        """Test response that meets no criteria."""
        criteria = [
            EvaluationCriteria(
                description="Mentions kubernetes",
                keywords=["kubernetes", "k8s"],
            ),
        ]

        response = "Docker is a containerization platform."
        score = evaluate_response(response, criteria)

        assert score.criteria_met == 0
        assert score.coverage_score == 0.0

    def test_case_insensitive_matching(self):
        """Test that keyword matching is case-insensitive."""
        criteria = [
            EvaluationCriteria(
                description="Mentions API",
                keywords=["API", "api"],
            ),
        ]

        response = "You should build an api for your service."
        score = evaluate_response(response, criteria)

        assert score.criteria_met == 1

    def test_empty_criteria(self):
        """Test with no criteria."""
        score = evaluate_response("Any response", [])

        assert score.criteria_met == 0
        assert score.criteria_total == 0
        assert score.coverage_score == 0.0

    def test_criteria_details_populated(self):
        """Test that criteria_details dict is populated correctly."""
        criteria = [
            EvaluationCriteria(description="Has foo", keywords=["foo"]),
            EvaluationCriteria(description="Has bar", keywords=["bar"]),
        ]

        response = "This has foo but not the other thing."
        score = evaluate_response(response, criteria)

        assert score.criteria_details["Has foo"] is True
        assert score.criteria_details["Has bar"] is False


class TestLoadTestDataset:
    """Tests for loading benchmark datasets."""

    def test_load_valid_dataset(self):
        """Test loading a valid benchmark file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(SAMPLE_BENCHMARK, f)
            f.flush()

            questions = load_test_dataset(f.name)

            assert len(questions) == 3
            assert questions[0].id == "tech-001"
            assert questions[0].category == "technical"
            assert len(questions[0].criteria) == 4

    def test_load_missing_file(self):
        """Test error handling for missing file."""
        with pytest.raises(FileNotFoundError):
            load_test_dataset("/nonexistent/path/benchmark.json")

    def test_criteria_keywords_loaded(self):
        """Test that criteria keywords are loaded correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(SAMPLE_BENCHMARK, f)
            f.flush()

            questions = load_test_dataset(f.name)
            first_criterion = questions[0].criteria[0]

            assert "over-fetching" in first_criterion.keywords
            assert first_criterion.required is True


class TestCalculateAggregateStats:
    """Tests for aggregate statistics calculation."""

    def test_aggregate_with_results(self):
        """Test aggregate calculation with mock results."""
        results = [
            BenchmarkResult(
                question_id="q1",
                question_category="technical",
                council_score=ResponseScore(3, 4, 0.75, 100, {}),
                single_model_scores={
                    "model-a": ResponseScore(2, 4, 0.5, 80, {}),
                    "model-b": ResponseScore(4, 4, 1.0, 120, {}),  # beats council
                },
                council_response="",
                single_model_responses={},
            ),
            BenchmarkResult(
                question_id="q2",
                question_category="reasoning",
                council_score=ResponseScore(4, 4, 1.0, 150, {}),
                single_model_scores={
                    "model-a": ResponseScore(3, 4, 0.75, 90, {}),
                    "model-b": ResponseScore(3, 4, 0.75, 100, {}),
                },
                council_response="",
                single_model_responses={},
            ),
        ]

        stats = calculate_aggregate_stats(results)

        assert stats["total_questions"] == 2
        assert stats["council_avg_coverage"] == 0.875  # (0.75 + 1.0) / 2
        assert "model-a" in stats["model_stats"]
        assert "model-b" in stats["model_stats"]
        # model-b beat council once (q1)
        assert stats["model_stats"]["model-b"]["wins_vs_council"] == 1

    def test_aggregate_empty_results(self):
        """Test aggregate with no results."""
        stats = calculate_aggregate_stats([])
        assert stats == {}


class TestPrintBenchmarkReport:
    """Tests for report generation."""

    def test_report_generation(self):
        """Test that report is generated without errors."""
        results = [
            BenchmarkResult(
                question_id="q1",
                question_category="technical",
                council_score=ResponseScore(3, 4, 0.75, 100, {}),
                single_model_scores={
                    "openai/gpt-4": ResponseScore(2, 4, 0.5, 80, {}),
                },
                council_response="",
                single_model_responses={},
            ),
        ]

        report = print_benchmark_report(results)

        assert "BENCHMARK RESULTS" in report
        assert "LLM Council" in report
        assert "0.75" in report  # council coverage


class TestCreateSampleBenchmark:
    """Tests for sample benchmark creation."""

    def test_create_sample_file(self):
        """Test sample benchmark file creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_benchmark.json"
            create_sample_benchmark_file(str(path))

            assert path.exists()

            with open(path) as f:
                data = json.load(f)

            assert "questions" in data
            assert len(data["questions"]) > 0
