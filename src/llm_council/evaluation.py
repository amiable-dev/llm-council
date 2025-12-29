"""Evaluation harness for benchmarking Council vs Single Model responses.

This module provides tools to empirically validate that council deliberation
produces better responses than individual models. Critical for ensuring
leaderboard data quality (prevent "Garbage In, Garbage Out").

Usage:
    from llm_council.evaluation import run_benchmark, load_test_dataset

    # Run full benchmark
    results = await run_benchmark("tests/data/benchmark.json")
    print_benchmark_report(results)
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class EvaluationCriteria:
    """A single evaluation criterion for a question."""

    description: str
    keywords: List[str] = field(default_factory=list)  # Keywords to look for
    required: bool = True  # Is this criterion required for a "good" answer?


@dataclass
class BenchmarkQuestion:
    """A question in the benchmark dataset."""

    id: str
    query: str
    criteria: List[EvaluationCriteria]
    category: str = "general"
    difficulty: str = "medium"  # easy, medium, hard
    reference_answer: Optional[str] = None


@dataclass
class ResponseScore:
    """Score for a single response."""

    criteria_met: int
    criteria_total: int
    coverage_score: float  # criteria_met / criteria_total
    response_length: int
    criteria_details: Dict[str, bool] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    question_id: str
    question_category: str
    council_score: ResponseScore
    single_model_scores: Dict[str, ResponseScore]  # model -> score
    council_response: str
    single_model_responses: Dict[str, str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


def evaluate_response(response: str, criteria: List[EvaluationCriteria]) -> ResponseScore:
    """Score a response against evaluation criteria.

    Uses keyword matching for objective scoring. For more sophisticated
    evaluation, consider using LLM-as-judge (see evaluate_with_llm_judge).

    Args:
        response: The model's response text
        criteria: List of evaluation criteria

    Returns:
        ResponseScore with coverage metrics
    """
    response_lower = response.lower()
    criteria_details = {}
    criteria_met = 0

    for criterion in criteria:
        # Check if any keywords are present in the response
        met = False
        if criterion.keywords:
            met = any(kw.lower() in response_lower for kw in criterion.keywords)
        else:
            # Fallback: check if criterion description words appear
            desc_words = criterion.description.lower().split()
            # Require at least 2 significant words to match
            significant_words = [w for w in desc_words if len(w) > 4]
            if significant_words:
                met = sum(1 for w in significant_words if w in response_lower) >= min(
                    2, len(significant_words)
                )

        criteria_details[criterion.description] = met
        if met:
            criteria_met += 1

    criteria_total = len(criteria)
    coverage_score = criteria_met / criteria_total if criteria_total > 0 else 0.0

    return ResponseScore(
        criteria_met=criteria_met,
        criteria_total=criteria_total,
        coverage_score=round(coverage_score, 3),
        response_length=len(response),
        criteria_details=criteria_details,
    )


def load_test_dataset(path: str) -> List[BenchmarkQuestion]:
    """Load benchmark questions from a JSON file.

    Expected format:
    {
        "questions": [
            {
                "id": "q001",
                "query": "What are the trade-offs between REST and GraphQL?",
                "category": "technical",
                "difficulty": "medium",
                "criteria": [
                    {
                        "description": "Mentions over-fetching/under-fetching",
                        "keywords": ["over-fetching", "under-fetching", "overfetch"],
                        "required": true
                    }
                ]
            }
        ]
    }
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark dataset not found: {path}")

    with open(path, "r") as f:
        data = json.load(f)

    questions = []
    for q in data.get("questions", []):
        criteria = [
            EvaluationCriteria(
                description=c["description"],
                keywords=c.get("keywords", []),
                required=c.get("required", True),
            )
            for c in q.get("criteria", [])
        ]
        questions.append(
            BenchmarkQuestion(
                id=q["id"],
                query=q["query"],
                criteria=criteria,
                category=q.get("category", "general"),
                difficulty=q.get("difficulty", "medium"),
                reference_answer=q.get("reference_answer"),
            )
        )

    return questions


async def run_benchmark(
    dataset_path: str,
    models: Optional[List[str]] = None,
    include_council: bool = True,
    verbose: bool = False,
) -> List[BenchmarkResult]:
    """Run the full benchmark suite.

    Compares council responses against individual model responses.

    Args:
        dataset_path: Path to benchmark JSON file
        models: List of models to benchmark (defaults to COUNCIL_MODELS)
        include_council: Whether to run the full council
        verbose: Print progress

    Returns:
        List of BenchmarkResult for each question
    """
    from llm_council.council import run_full_council
    from llm_council.openrouter import query_model

    # ADR-032: Migrated to unified_config
    from llm_council.unified_config import get_config

    if models is None:
        models = get_config().council.models

    questions = load_test_dataset(dataset_path)
    results = []

    for i, question in enumerate(questions):
        if verbose:
            print(f"[{i+1}/{len(questions)}] Benchmarking: {question.id}")

        single_model_scores = {}
        single_model_responses = {}

        # Get single-model responses
        for model in models:
            if verbose:
                print(f"  - Querying {model}...")
            try:
                response = await query_model(model, question.query)
                content = response.get("content", "") if response else ""
                single_model_responses[model] = content
                single_model_scores[model] = evaluate_response(content, question.criteria)
            except Exception as e:
                if verbose:
                    print(f"    Error: {e}")
                single_model_responses[model] = ""
                single_model_scores[model] = ResponseScore(0, len(question.criteria), 0.0, 0, {})

        # Get council response
        council_response = ""
        council_score = ResponseScore(0, len(question.criteria), 0.0, 0, {})

        if include_council:
            if verbose:
                print(f"  - Running council...")
            try:
                stage1, stage2, stage3, metadata = await run_full_council(question.query)
                council_response = stage3.get("final_answer", "") if stage3 else ""
                council_score = evaluate_response(council_response, question.criteria)
            except Exception as e:
                if verbose:
                    print(f"    Council error: {e}")

        results.append(
            BenchmarkResult(
                question_id=question.id,
                question_category=question.category,
                council_score=council_score,
                single_model_scores=single_model_scores,
                council_response=council_response,
                single_model_responses=single_model_responses,
            )
        )

    return results


def calculate_aggregate_stats(results: List[BenchmarkResult]) -> Dict[str, Any]:
    """Calculate aggregate statistics from benchmark results.

    Returns:
        Dict with avg coverage, win rates, etc.
    """
    if not results:
        return {}

    # Collect all models that were benchmarked
    all_models = set()
    for r in results:
        all_models.update(r.single_model_scores.keys())

    # Calculate averages
    council_coverages = [r.council_score.coverage_score for r in results if r.council_score]
    council_avg = sum(council_coverages) / len(council_coverages) if council_coverages else 0

    model_stats = {}
    for model in all_models:
        coverages = [
            r.single_model_scores[model].coverage_score
            for r in results
            if model in r.single_model_scores
        ]
        wins_vs_council = sum(
            1
            for r in results
            if model in r.single_model_scores
            and r.single_model_scores[model].coverage_score > r.council_score.coverage_score
        )

        model_stats[model] = {
            "avg_coverage": round(sum(coverages) / len(coverages), 3) if coverages else 0,
            "wins_vs_council": wins_vs_council,
            "win_rate_vs_council": round(wins_vs_council / len(results), 3) if results else 0,
            "samples": len(coverages),
        }

    return {
        "total_questions": len(results),
        "council_avg_coverage": round(council_avg, 3),
        "model_stats": model_stats,
        "categories": list(set(r.question_category for r in results)),
    }


def print_benchmark_report(results: List[BenchmarkResult]) -> str:
    """Generate a human-readable benchmark report.

    Returns:
        Formatted report string
    """
    stats = calculate_aggregate_stats(results)

    lines = [
        "=" * 70,
        "BENCHMARK RESULTS",
        "=" * 70,
        f"Total Questions: {stats['total_questions']}",
        f"Categories: {', '.join(stats['categories'])}",
        "",
        "-" * 70,
        f"{'Model/System':<30} {'Avg Coverage':<15} {'Win Rate vs Council':<20}",
        "-" * 70,
        f"{'LLM Council':<30} {stats['council_avg_coverage']:<15.3f} {'-':<20}",
    ]

    for model, model_stat in stats.get("model_stats", {}).items():
        # Shorten model name for display
        short_name = model.split("/")[-1][:28]
        lines.append(
            f"{short_name:<30} {model_stat['avg_coverage']:<15.3f} "
            f"{model_stat['win_rate_vs_council']*100:.1f}%"
        )

    lines.extend(
        [
            "-" * 70,
            "",
            "Coverage = fraction of evaluation criteria met in response",
            "Win Rate = how often single model beat council",
            "=" * 70,
        ]
    )

    report = "\n".join(lines)
    print(report)
    return report


def save_results(results: List[BenchmarkResult], path: str) -> None:
    """Save benchmark results to JSON file."""
    output = {
        "timestamp": datetime.now().isoformat(),
        "stats": calculate_aggregate_stats(results),
        "results": [
            {
                "question_id": r.question_id,
                "category": r.question_category,
                "council_coverage": r.council_score.coverage_score,
                "council_criteria_met": r.council_score.criteria_met,
                "single_model_coverages": {
                    model: score.coverage_score for model, score in r.single_model_scores.items()
                },
            }
            for r in results
        ],
    }

    with open(path, "w") as f:
        json.dump(output, f, indent=2)


# Sample benchmark dataset for testing
SAMPLE_BENCHMARK = {
    "questions": [
        {
            "id": "tech-001",
            "query": "What are the key differences between REST and GraphQL APIs?",
            "category": "technical",
            "difficulty": "medium",
            "criteria": [
                {
                    "description": "Explains data fetching differences",
                    "keywords": [
                        "over-fetching",
                        "under-fetching",
                        "single endpoint",
                        "multiple endpoints",
                    ],
                    "required": True,
                },
                {
                    "description": "Mentions schema/type system",
                    "keywords": ["schema", "type", "typed", "introspection"],
                    "required": True,
                },
                {
                    "description": "Discusses caching implications",
                    "keywords": ["cache", "caching", "HTTP cache", "CDN"],
                    "required": False,
                },
                {
                    "description": "Mentions versioning approaches",
                    "keywords": ["version", "versioning", "evolution", "deprecation"],
                    "required": False,
                },
            ],
        },
        {
            "id": "tech-002",
            "query": "Explain the CAP theorem and its practical implications for distributed databases.",
            "category": "technical",
            "difficulty": "hard",
            "criteria": [
                {
                    "description": "Defines all three properties (Consistency, Availability, Partition tolerance)",
                    "keywords": ["consistency", "availability", "partition"],
                    "required": True,
                },
                {
                    "description": "Explains the trade-off (can only have 2 of 3)",
                    "keywords": ["trade-off", "choose two", "sacrifice", "cannot have all"],
                    "required": True,
                },
                {
                    "description": "Gives practical database examples",
                    "keywords": ["MongoDB", "Cassandra", "PostgreSQL", "DynamoDB", "Spanner"],
                    "required": False,
                },
                {
                    "description": "Mentions eventual consistency",
                    "keywords": ["eventual consistency", "eventually consistent"],
                    "required": False,
                },
            ],
        },
        {
            "id": "reasoning-001",
            "query": "A startup has $500k runway and needs to choose between hiring 2 senior engineers at $150k each or 4 junior engineers at $75k each. What factors should they consider?",
            "category": "reasoning",
            "difficulty": "medium",
            "criteria": [
                {
                    "description": "Considers productivity differences",
                    "keywords": ["productivity", "output", "velocity", "experience", "ramp-up"],
                    "required": True,
                },
                {
                    "description": "Mentions mentorship/management overhead",
                    "keywords": ["mentor", "management", "oversight", "training", "guidance"],
                    "required": True,
                },
                {
                    "description": "Discusses risk factors",
                    "keywords": ["risk", "bus factor", "turnover", "retention"],
                    "required": False,
                },
                {
                    "description": "Considers company stage/needs",
                    "keywords": ["stage", "growth", "scale", "early-stage", "startup"],
                    "required": False,
                },
            ],
        },
    ]
}


def create_sample_benchmark_file(path: str = "benchmark_sample.json") -> None:
    """Create a sample benchmark file for testing."""
    with open(path, "w") as f:
        json.dump(SAMPLE_BENCHMARK, f, indent=2)
    print(f"Created sample benchmark file: {path}")
