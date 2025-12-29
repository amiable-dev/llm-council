"""Basic tests for council orchestration."""

import pytest
from llm_council.council import parse_ranking_from_text, calculate_aggregate_rankings


def test_council_imports():
    """Test that council module can be imported."""
    from llm_council import council

    assert hasattr(council, "run_full_council")
    assert hasattr(council, "stage1_collect_responses")
    assert hasattr(council, "stage2_collect_rankings")
    assert hasattr(council, "stage3_synthesize_final")


def test_parse_ranking_from_text():
    """Test ranking parser function."""
    from llm_council.council import parse_ranking_from_text

    test_text = """
    Some analysis here...
    
    FINAL RANKING:
    1. Response A
    2. Response B
    3. Response C
    """

    result = parse_ranking_from_text(test_text)
    # New API returns dict with ranking and scores
    assert "ranking" in result
    assert result["ranking"] == ["Response A", "Response B", "Response C"]


def test_calculate_aggregate_rankings():
    """Test aggregate ranking calculation."""
    from llm_council.council import calculate_aggregate_rankings

    stage2_results = [
        {
            "model": "model1",
            "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
            "parsed_ranking": {"ranking": ["Response A", "Response B"], "scores": {}},
        },
        {
            "model": "model2",
            "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
            "parsed_ranking": {"ranking": ["Response B", "Response A"], "scores": {}},
        },
    ]

    label_to_model = {"Response A": "openai/gpt-4", "Response B": "anthropic/claude"}

    result = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Both models should be in results
    assert len(result) == 2
    assert all("model" in r for r in result)
    # New API uses average_position and average_score
    assert all("average_position" in r for r in result)
    assert all("rank" in r for r in result)


def test_parse_ranking_json_format():
    """Test JSON ranking parser."""
    test_text = """
    Here is my evaluation...

    ```json
    {
      "ranking": ["Response B", "Response A", "Response C"],
      "scores": {
        "Response A": 7,
        "Response B": 9,
        "Response C": 5
      }
    }
    ```
    """

    result = parse_ranking_from_text(test_text)
    assert result["ranking"] == ["Response B", "Response A", "Response C"]
    assert result["scores"]["Response A"] == 7
    assert result["scores"]["Response B"] == 9
    assert result["scores"]["Response C"] == 5


def test_parse_ranking_refusal_detection():
    """Test that safety refusals are detected."""
    refusal_texts = [
        "I cannot evaluate these responses as they contain harmful content.",
        "I'm not able to rank these responses.",
        "I must decline to provide a ranking.",
        "I apologize, but I cannot compare these responses.",
    ]

    for text in refusal_texts:
        result = parse_ranking_from_text(text)
        assert result.get("abstained") is True, f"Failed to detect refusal in: {text}"
        assert "abstention_reason" in result


def test_parse_ranking_no_false_positive_refusal():
    """Test that normal evaluations aren't marked as refusals."""
    test_text = """
    I can evaluate these responses. Here's my analysis...

    ```json
    {
      "ranking": ["Response A", "Response B"],
      "scores": {"Response A": 8, "Response B": 6}
    }
    ```
    """

    result = parse_ranking_from_text(test_text)
    assert result.get("abstained") is not True
    assert result["ranking"] == ["Response A", "Response B"]


def test_borda_count_calculation():
    """Test normalized Borda count ranking aggregation.

    With normalization, scores are in [0, 1] range regardless of council size.
    Formula: normalized_score = raw_borda / (num_candidates - 1)
    """
    # 3 candidates, 2 reviewers, max_borda = 2
    # Reviewer 1: A > B > C
    #   A gets 2/2=1.0, B gets 1/2=0.5, C gets 0/2=0.0
    # Reviewer 2: B > A > C
    #   B gets 2/2=1.0, A gets 1/2=0.5, C gets 0/2=0.0
    # Average: A=(1.0+0.5)/2=0.75, B=(0.5+1.0)/2=0.75, C=0.0

    stage2_results = [
        {
            "model": "reviewer1",
            "ranking": "",
            "parsed_ranking": {
                "ranking": ["Response A", "Response B", "Response C"],
                "scores": {"Response A": 9, "Response B": 7, "Response C": 5},
            },
        },
        {
            "model": "reviewer2",
            "ranking": "",
            "parsed_ranking": {
                "ranking": ["Response B", "Response A", "Response C"],
                "scores": {"Response A": 7, "Response B": 9, "Response C": 5},
            },
        },
    ]

    label_to_model = {"Response A": "model_a", "Response B": "model_b", "Response C": "model_c"}

    result = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Check Borda scores exist
    assert all("borda_score" in r for r in result)

    # A and B should be tied with normalized borda_score of 0.75 each
    scores_by_model = {r["model"]: r["borda_score"] for r in result}
    assert scores_by_model["model_a"] == 0.75
    assert scores_by_model["model_b"] == 0.75
    assert scores_by_model["model_c"] == 0.0


def test_borda_normalization_council_size_independence():
    """Test that normalized Borda scores are comparable across council sizes.

    Critical fix for issue #14: Without normalization, a 3-model council
    produces max score of 2, while a 5-model council produces max of 4.
    With normalization, 1st place always gets 1.0 regardless of council size.
    """
    # 3-candidate council: max_borda = 2
    stage2_small = [
        {
            "model": "reviewer1",
            "ranking": "",
            "parsed_ranking": {"ranking": ["Response A", "Response B", "Response C"], "scores": {}},
        },
    ]
    label_small = {"Response A": "model_a", "Response B": "model_b", "Response C": "model_c"}

    # 5-candidate council: max_borda = 4
    stage2_large = [
        {
            "model": "reviewer1",
            "ranking": "",
            "parsed_ranking": {
                "ranking": ["Response A", "Response B", "Response C", "Response D", "Response E"],
                "scores": {},
            },
        },
    ]
    label_large = {
        "Response A": "model_a",
        "Response B": "model_b",
        "Response C": "model_c",
        "Response D": "model_d",
        "Response E": "model_e",
    }

    result_small = calculate_aggregate_rankings(stage2_small, label_small)
    result_large = calculate_aggregate_rankings(stage2_large, label_large)

    # 1st place should get 1.0 in BOTH council sizes
    scores_small = {r["model"]: r["borda_score"] for r in result_small}
    scores_large = {r["model"]: r["borda_score"] for r in result_large}

    assert scores_small["model_a"] == 1.0, "3-model council: 1st place should be 1.0"
    assert scores_large["model_a"] == 1.0, "5-model council: 1st place should be 1.0"

    # Last place should get 0.0 in BOTH
    assert scores_small["model_c"] == 0.0, "3-model council: last place should be 0.0"
    assert scores_large["model_e"] == 0.0, "5-model council: last place should be 0.0"


def test_borda_count_excludes_abstentions():
    """Test that abstained reviewers are excluded from Borda count."""
    stage2_results = [
        {
            "model": "reviewer1",
            "ranking": "",
            "parsed_ranking": {"ranking": ["Response A", "Response B"], "scores": {}},
        },
        {
            "model": "reviewer2",
            "ranking": "",
            "parsed_ranking": {
                "abstained": True,
                "abstention_reason": "Safety refusal",
                "ranking": [],
                "scores": {},
            },
        },
    ]

    label_to_model = {"Response A": "model_a", "Response B": "model_b"}

    result = calculate_aggregate_rankings(stage2_results, label_to_model)

    # Only 1 vote should count (reviewer2 abstained)
    assert all(r["vote_count"] == 1 for r in result)


def test_detect_score_rank_mismatch():
    """Test detection of score/rank mismatches."""
    from llm_council.council import detect_score_rank_mismatch

    # Case 1: No mismatch - scores match ranking order
    ranking = ["Response A", "Response B", "Response C"]
    scores = {"Response A": 9, "Response B": 7, "Response C": 5}
    assert detect_score_rank_mismatch(ranking, scores) is False

    # Case 2: Mismatch - ranking says A > B > C, but scores say B > A > C
    ranking = ["Response A", "Response B", "Response C"]
    scores = {"Response A": 7, "Response B": 9, "Response C": 5}
    assert detect_score_rank_mismatch(ranking, scores) is True

    # Case 3: Empty inputs
    assert detect_score_rank_mismatch([], {}) is False
    assert detect_score_rank_mismatch(["A"], {}) is False
    assert detect_score_rank_mismatch([], {"A": 5}) is False

    # Case 4: Single item (no comparison possible)
    assert detect_score_rank_mismatch(["A"], {"A": 5}) is False

    # Case 5: Partial scores - only check labels with scores
    ranking = ["Response A", "Response B", "Response C"]
    scores = {"Response A": 9, "Response B": 7}  # C has no score
    assert detect_score_rank_mismatch(ranking, scores) is False


def test_parse_ranking_detects_mismatch():
    """Test that parse_ranking_from_text flags score/rank mismatches."""
    # Mismatched: ranking says B > A > C, but scores say A > B > C
    test_text = """
    Here is my evaluation...

    ```json
    {
      "ranking": ["Response B", "Response A", "Response C"],
      "scores": {
        "Response A": 9,
        "Response B": 7,
        "Response C": 5
      }
    }
    ```
    """

    result = parse_ranking_from_text(test_text)
    assert result["ranking"] == ["Response B", "Response A", "Response C"]
    assert result.get("score_rank_mismatch") is True


def test_parse_ranking_no_mismatch():
    """Test that parse_ranking_from_text doesn't flag consistent scores."""
    # Consistent: ranking and scores agree
    test_text = """
    ```json
    {
      "ranking": ["Response A", "Response B", "Response C"],
      "scores": {
        "Response A": 9,
        "Response B": 7,
        "Response C": 5
      }
    }
    ```
    """

    result = parse_ranking_from_text(test_text)
    assert result["ranking"] == ["Response A", "Response B", "Response C"]
    assert result.get("score_rank_mismatch") is not True
