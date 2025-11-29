"""Basic tests for council orchestration."""
import pytest


def test_council_imports():
    """Test that council module can be imported."""
    from llm_council_mcp import council
    assert hasattr(council, 'run_full_council')
    assert hasattr(council, 'stage1_collect_responses')
    assert hasattr(council, 'stage2_collect_rankings')
    assert hasattr(council, 'stage3_synthesize_final')


def test_parse_ranking_from_text():
    """Test ranking parser function."""
    from llm_council_mcp.council import parse_ranking_from_text
    
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
    from llm_council_mcp.council import calculate_aggregate_rankings
    
    stage2_results = [
        {
            "model": "model1",
            "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
            "parsed_ranking": {
                "ranking": ["Response A", "Response B"],
                "scores": {}
            }
        },
        {
            "model": "model2", 
            "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
            "parsed_ranking": {
                "ranking": ["Response B", "Response A"],
                "scores": {}
            }
        },
    ]
    
    label_to_model = {
        "Response A": "openai/gpt-4",
        "Response B": "anthropic/claude"
    }
    
    result = calculate_aggregate_rankings(stage2_results, label_to_model)
    
    # Both models should be in results
    assert len(result) == 2
    assert all("model" in r for r in result)
    # New API uses average_position and average_score
    assert all("average_position" in r for r in result)
    assert all("rank" in r for r in result)
