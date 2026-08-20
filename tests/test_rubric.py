"""Tests for ADR-016: Structured Rubric Scoring.

TDD tests for multi-dimensional rubric evaluation with accuracy ceiling.
"""

import pytest
from dataclasses import asdict

from llm_council.rubric import (
    RubricScore,
    DEFAULT_RUBRIC_WEIGHTS,
    UPDATED_RUBRIC_WEIGHTS,
    calculate_weighted_score,
    calculate_weighted_score_with_accuracy_ceiling,
    parse_rubric_evaluation,
    validate_weights,
    InvalidWeightsError,
)


class TestRubricScore:
    """Tests for the RubricScore dataclass."""

    def test_rubric_score_creation(self):
        """Test creating a RubricScore with all dimensions."""
        score = RubricScore(
            accuracy=8,
            relevance=7,
            completeness=9,
            conciseness=6,
            clarity=8,
        )
        assert score.accuracy == 8
        assert score.relevance == 7
        assert score.completeness == 9
        assert score.conciseness == 6
        assert score.clarity == 8

    def test_rubric_score_to_dict(self):
        """Test converting RubricScore to dict."""
        score = RubricScore(
            accuracy=8,
            relevance=7,
            completeness=9,
            conciseness=6,
            clarity=8,
        )
        d = asdict(score)
        assert d["accuracy"] == 8
        assert d["relevance"] == 7
        assert "notes" in d

    def test_rubric_score_with_notes(self):
        """Test RubricScore with notes field."""
        score = RubricScore(
            accuracy=9,
            relevance=8,
            completeness=8,
            conciseness=7,
            clarity=9,
            notes="Excellent response with minor verbosity",
        )
        assert score.notes == "Excellent response with minor verbosity"

    def test_rubric_score_optional_overall(self):
        """Test RubricScore with pre-calculated overall."""
        score = RubricScore(
            accuracy=8,
            relevance=7,
            completeness=9,
            conciseness=6,
            clarity=8,
            overall=7.65,
        )
        assert score.overall == 7.65


class TestDefaultWeights:
    """Tests for weight configuration."""

    def test_default_weights_sum_to_one(self):
        """Default weights must sum to 1.0."""
        total = sum(DEFAULT_RUBRIC_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_updated_weights_sum_to_one(self):
        """Updated (post-council) weights must sum to 1.0."""
        total = sum(UPDATED_RUBRIC_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_default_weights_has_all_dimensions(self):
        """Default weights include all five dimensions."""
        expected = {"accuracy", "relevance", "completeness", "conciseness", "clarity"}
        assert set(DEFAULT_RUBRIC_WEIGHTS.keys()) == expected

    def test_accuracy_is_highest_weight(self):
        """Accuracy should have the highest weight."""
        accuracy_weight = DEFAULT_RUBRIC_WEIGHTS["accuracy"]
        for dim, weight in DEFAULT_RUBRIC_WEIGHTS.items():
            if dim != "accuracy":
                assert accuracy_weight >= weight


class TestValidateWeights:
    """Tests for weight validation."""

    def test_valid_weights_pass(self):
        """Valid weights (sum to 1.0) should pass."""
        weights = {
            "accuracy": 0.35,
            "relevance": 0.10,
            "completeness": 0.20,
            "conciseness": 0.15,
            "clarity": 0.20,
        }
        # Should not raise
        validate_weights(weights)

    def test_weights_not_summing_to_one_fails(self):
        """Weights not summing to 1.0 should raise error."""
        weights = {
            "accuracy": 0.50,
            "relevance": 0.10,
            "completeness": 0.20,
            "conciseness": 0.15,
            "clarity": 0.20,
        }
        with pytest.raises(InvalidWeightsError):
            validate_weights(weights)

    def test_missing_dimension_fails(self):
        """Missing a dimension should raise error."""
        weights = {
            "accuracy": 0.40,
            "completeness": 0.30,
            "conciseness": 0.15,
            "clarity": 0.15,
            # missing "relevance"
        }
        with pytest.raises(InvalidWeightsError):
            validate_weights(weights)


class TestCalculateWeightedScore:
    """Tests for basic weighted score calculation."""

    def test_perfect_scores(self):
        """Perfect scores (all 10s) should yield 10.0."""
        scores = {
            "accuracy": 10,
            "relevance": 10,
            "completeness": 10,
            "conciseness": 10,
            "clarity": 10,
        }
        result = calculate_weighted_score(scores)
        assert result == 10.0

    def test_all_zeros(self):
        """All zero scores should yield 0.0."""
        scores = {
            "accuracy": 0,
            "relevance": 0,
            "completeness": 0,
            "conciseness": 0,
            "clarity": 0,
        }
        result = calculate_weighted_score(scores)
        assert result == 0.0

    def test_weighted_calculation(self):
        """Test specific weighted calculation."""
        scores = {
            "accuracy": 8,  # 0.35 * 8 = 2.80
            "relevance": 7,  # 0.10 * 7 = 0.70
            "completeness": 9,  # 0.20 * 9 = 1.80
            "conciseness": 6,  # 0.15 * 6 = 0.90
            "clarity": 8,  # 0.20 * 8 = 1.60
        }
        # Total: 2.80 + 0.70 + 1.80 + 0.90 + 1.60 = 7.80
        result = calculate_weighted_score(scores, UPDATED_RUBRIC_WEIGHTS)
        assert result == 7.8

    def test_custom_weights(self):
        """Test with custom weight configuration."""
        scores = {
            "accuracy": 10,
            "relevance": 5,
            "completeness": 5,
            "conciseness": 5,
            "clarity": 5,
        }
        # Heavy accuracy weighting
        custom_weights = {
            "accuracy": 0.60,
            "relevance": 0.10,
            "completeness": 0.10,
            "conciseness": 0.10,
            "clarity": 0.10,
        }
        result = calculate_weighted_score(scores, custom_weights)
        # 0.60 * 10 + 0.10 * 5 * 4 = 6.0 + 2.0 = 8.0
        assert result == 8.0

    def test_rounding(self):
        """Test that result is rounded to 2 decimal places."""
        scores = {
            "accuracy": 7,
            "relevance": 7,
            "completeness": 7,
            "conciseness": 7,
            "clarity": 7,
        }
        result = calculate_weighted_score(scores)
        assert result == 7.0
        assert isinstance(result, float)


class TestAccuracyCeiling:
    """Tests for accuracy ceiling mechanism (ADR-016 council recommendation)."""

    def test_high_accuracy_no_ceiling(self):
        """Accuracy >= 7 should have no ceiling applied."""
        scores = {
            "accuracy": 9,
            "relevance": 9,
            "completeness": 9,
            "conciseness": 9,
            "clarity": 9,
        }
        result = calculate_weighted_score_with_accuracy_ceiling(scores)
        # No ceiling, should be 9.0
        assert result == 9.0

    def test_accuracy_7_no_ceiling(self):
        """Accuracy exactly 7 should have no ceiling."""
        scores = {
            "accuracy": 7,
            "relevance": 9,
            "completeness": 9,
            "conciseness": 9,
            "clarity": 9,
        }
        result = calculate_weighted_score_with_accuracy_ceiling(scores)
        # Base: 0.35*7 + 0.10*9 + 0.20*9 + 0.15*9 + 0.20*9 = 2.45 + 5.85 = 8.30
        # No ceiling at accuracy=7
        assert result == 8.3

    def test_medium_accuracy_ceiling_at_7(self):
        """Accuracy 5-6 should cap score at 7.0."""
        scores = {
            "accuracy": 6,
            "relevance": 10,
            "completeness": 10,
            "conciseness": 10,
            "clarity": 10,
        }
        result = calculate_weighted_score_with_accuracy_ceiling(scores)
        # Base would be: 0.35*6 + 0.65*10 = 2.1 + 6.5 = 8.6
        # But ceiling is 7.0 because accuracy < 7
        assert result == 7.0

    def test_accuracy_5_ceiling_at_7(self):
        """Accuracy exactly 5 should still cap at 7.0."""
        scores = {
            "accuracy": 5,
            "relevance": 9,
            "completeness": 9,
            "conciseness": 9,
            "clarity": 9,
        }
        result = calculate_weighted_score_with_accuracy_ceiling(scores)
        assert result == 7.0

    def test_low_accuracy_ceiling_at_4(self):
        """Accuracy < 5 should cap score at 4.0."""
        scores = {
            "accuracy": 4,
            "relevance": 10,
            "completeness": 10,
            "conciseness": 10,
            "clarity": 10,
        }
        result = calculate_weighted_score_with_accuracy_ceiling(scores)
        # Base would be high, but ceiling is 4.0
        assert result == 4.0

    def test_hallucination_cannot_rank_high(self):
        """Well-written hallucination (acc=3, others=9) should cap at 4.0.

        This is the key ADR-016 council insight: a confident lie cannot
        score well no matter how well-written it is.
        """
        scores = {
            "accuracy": 3,  # Hallucination/factual error
            "relevance": 9,  # Addresses the question
            "completeness": 9,  # Comprehensive
            "conciseness": 9,  # Well-written
            "clarity": 9,  # Clear presentation
        }
        result = calculate_weighted_score_with_accuracy_ceiling(scores)
        # Without ceiling: 0.35*3 + 0.65*9 = 1.05 + 5.85 = 6.90
        # With ceiling (acc < 5): max 4.0
        assert result == 4.0

    def test_very_low_accuracy_caps_at_4(self):
        """Accuracy of 1 should also cap at 4.0."""
        scores = {
            "accuracy": 1,
            "relevance": 10,
            "completeness": 10,
            "conciseness": 10,
            "clarity": 10,
        }
        result = calculate_weighted_score_with_accuracy_ceiling(scores)
        assert result == 4.0

    def test_ceiling_does_not_inflate(self):
        """Ceiling should not increase a naturally low score."""
        scores = {
            "accuracy": 3,
            "relevance": 2,
            "completeness": 2,
            "conciseness": 2,
            "clarity": 2,
        }
        result = calculate_weighted_score_with_accuracy_ceiling(scores)
        # Base: 0.35*3 + 0.65*2 = 1.05 + 1.30 = 2.35
        # Ceiling is 4.0, but base is lower, so use base
        assert result == 2.35

    def test_accuracy_zero_caps_at_4(self):
        """Accuracy of 0 (complete nonsense) should cap at 4.0."""
        scores = {
            "accuracy": 0,
            "relevance": 10,
            "completeness": 10,
            "conciseness": 10,
            "clarity": 10,
        }
        result = calculate_weighted_score_with_accuracy_ceiling(scores)
        assert result == 4.0


class TestParseRubricEvaluation:
    """Tests for parsing rubric JSON from model responses."""

    def test_parse_valid_json(self):
        """Parse well-formed rubric evaluation JSON."""
        response_text = """
Here is my evaluation of the responses.

Response A is accurate and comprehensive.
Response B has some issues with completeness.

```json
{
  "ranking": ["Response A", "Response B"],
  "evaluations": {
    "Response A": {
      "accuracy": 9,
      "relevance": 8,
      "completeness": 9,
      "conciseness": 7,
      "clarity": 8,
      "overall": 8.35,
      "notes": "Well-researched and accurate"
    },
    "Response B": {
      "accuracy": 6,
      "relevance": 7,
      "completeness": 5,
      "conciseness": 8,
      "clarity": 7,
      "overall": 6.35,
      "notes": "Missing key details"
    }
  }
}
```
"""
        result = parse_rubric_evaluation(response_text)

        assert result is not None
        assert result["ranking"] == ["Response A", "Response B"]
        assert "evaluations" in result
        assert result["evaluations"]["Response A"]["accuracy"] == 9
        assert result["evaluations"]["Response B"]["completeness"] == 5

    def test_parse_json_without_code_block(self):
        """Parse JSON that's not in a code block."""
        response_text = """
My evaluation:

{
  "ranking": ["Response A"],
  "evaluations": {
    "Response A": {
      "accuracy": 8,
      "relevance": 8,
      "completeness": 8,
      "conciseness": 8,
      "clarity": 8,
      "overall": 8.0,
      "notes": "Good overall"
    }
  }
}
"""
        result = parse_rubric_evaluation(response_text)
        assert result is not None
        assert result["ranking"] == ["Response A"]

    def test_parse_invalid_json_returns_none(self):
        """Invalid JSON should return None for fallback handling."""
        response_text = """
I think Response A is best because it's accurate.
Response B is not as good.
"""
        result = parse_rubric_evaluation(response_text)
        assert result is None

    def test_parse_partial_rubric_returns_none(self):
        """JSON missing required fields should return None."""
        response_text = """
```json
{
  "ranking": ["Response A", "Response B"]
}
```
"""
        # Missing "evaluations" field
        result = parse_rubric_evaluation(response_text)
        assert result is None

    def test_parse_empty_response(self):
        """Empty response should return None."""
        result = parse_rubric_evaluation("")
        assert result is None

    def test_parse_extracts_from_long_response(self):
        """Should extract JSON from a long response with other content."""
        response_text = """
Let me analyze each response carefully.

## Analysis

### Response A
This response demonstrates strong factual accuracy and addresses the question directly.
The structure is clear and the explanations are well-organized.

### Response B
This response has some issues with accuracy and misses a few key points.

## Final Assessment

Based on my analysis, Response A is the better answer.

```json
{
  "ranking": ["Response A", "Response B"],
  "evaluations": {
    "Response A": {
      "accuracy": 9,
      "relevance": 9,
      "completeness": 8,
      "conciseness": 7,
      "clarity": 9,
      "overall": 8.55,
      "notes": "Strong accuracy and clarity"
    },
    "Response B": {
      "accuracy": 5,
      "relevance": 7,
      "completeness": 6,
      "conciseness": 8,
      "clarity": 7,
      "overall": 6.15,
      "notes": "Accuracy issues noted"
    }
  }
}
```

That concludes my evaluation.
"""
        result = parse_rubric_evaluation(response_text)
        assert result is not None
        assert result["evaluations"]["Response A"]["accuracy"] == 9
        assert result["evaluations"]["Response B"]["accuracy"] == 5


class TestFallbackBehavior:
    """Tests for fallback behavior when rubric parsing fails."""

    def test_fallback_returns_none_for_invalid_json(self):
        """When rubric parsing fails, should return None for fallback to holistic."""
        # Response without proper JSON structure
        response_text = """
I've evaluated the responses.

Response A is better because it's more accurate.
Response B lacks completeness.

FINAL RANKING:
1. Response A
2. Response B
"""
        result = parse_rubric_evaluation(response_text)
        # Should return None, allowing fallback to holistic scoring
        assert result is None

    def test_fallback_holistic_ranking_still_parseable(self):
        """Holistic format should be parseable by the main council parser."""
        from llm_council.council import parse_ranking_from_text

        response_text = """
Let me evaluate these responses.

Response A is very accurate and complete.
Response B has some issues.

```json
{
  "ranking": ["Response A", "Response B"],
  "scores": {
    "Response A": 8,
    "Response B": 6
  }
}
```
"""
        # Rubric parser should return None (no evaluations field)
        rubric_result = parse_rubric_evaluation(response_text)
        assert rubric_result is None

        # But holistic parser should still work
        holistic_result = parse_ranking_from_text(response_text)
        assert holistic_result["ranking"] == ["Response A", "Response B"]
        assert holistic_result["scores"]["Response A"] == 8

    def test_malformed_evaluations_returns_none(self):
        """Malformed evaluations structure should return None."""
        response_text = """
```json
{
  "ranking": ["Response A"],
  "evaluations": "not a dict"
}
```
"""
        result = parse_rubric_evaluation(response_text)
        # Should return None because evaluations is not a dict
        assert result is None or not isinstance(result.get("evaluations"), dict)


class TestRubricPipelineIntegration:
    """Tests for rubric scoring integration with council pipeline."""

    def test_stage2_rubric_score_calculation(self):
        """Test that Stage 2 correctly calculates rubric scores."""
        from llm_council.rubric import (
            calculate_weighted_score_with_accuracy_ceiling,
            UPDATED_RUBRIC_WEIGHTS,
        )

        # Simulate parsed rubric evaluation from Stage 2
        evaluations = {
            "Response A": {
                "accuracy": 9,
                "relevance": 8,
                "completeness": 8,
                "conciseness": 7,
                "clarity": 8,
            },
            "Response B": {
                "accuracy": 4,
                "relevance": 9,
                "completeness": 9,
                "conciseness": 9,
                "clarity": 9,
            },
        }

        # Calculate scores as council.py would
        scores_with_ceiling = {}
        for resp_label, eval_data in evaluations.items():
            dimension_scores = {
                "accuracy": eval_data.get("accuracy", 5),
                "relevance": eval_data.get("relevance", 5),
                "completeness": eval_data.get("completeness", 5),
                "conciseness": eval_data.get("conciseness", 5),
                "clarity": eval_data.get("clarity", 5),
            }
            overall = calculate_weighted_score_with_accuracy_ceiling(
                dimension_scores, UPDATED_RUBRIC_WEIGHTS
            )
            scores_with_ceiling[resp_label] = overall

        # Response A: high accuracy, no ceiling
        # 0.35*9 + 0.10*8 + 0.20*8 + 0.15*7 + 0.20*8 = 3.15 + 0.80 + 1.60 + 1.05 + 1.60 = 8.20
        assert scores_with_ceiling["Response A"] == 8.2

        # Response B: low accuracy (4), ceiling at 4.0
        assert scores_with_ceiling["Response B"] == 4.0

    def test_aggregate_rankings_preserve_rubric_scores(self):
        """Test that aggregate rankings work with rubric scores."""
        # Simulate stage2_results with rubric scoring
        stage2_results = [
            {
                "model": "reviewer-1",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 8.2, "Response B": 4.0},
                    "rubric_scoring": True,
                },
            },
            {
                "model": "reviewer-2",
                "parsed_ranking": {
                    "ranking": ["Response A", "Response B"],
                    "scores": {"Response A": 7.5, "Response B": 5.0},
                    "rubric_scoring": True,
                },
            },
        ]
        label_to_model = {
            "Response A": "model-a",
            "Response B": "model-b",
        }

        from llm_council.council import calculate_aggregate_rankings

        rankings = calculate_aggregate_rankings(stage2_results, label_to_model)

        # model-a should rank higher (better scores)
        assert rankings[0]["model"] == "model-a"
        assert rankings[0]["rank"] == 1
        assert rankings[1]["model"] == "model-b"
        assert rankings[1]["rank"] == 2


class TestRubricIntegration:
    """Integration tests combining scoring and parsing."""

    def test_parsed_scores_calculate_correctly(self):
        """Parse rubric and verify weighted calculation matches."""
        response_text = """
```json
{
  "ranking": ["Response A"],
  "evaluations": {
    "Response A": {
      "accuracy": 8,
      "relevance": 7,
      "completeness": 9,
      "conciseness": 6,
      "clarity": 8,
      "overall": 7.8,
      "notes": "Good response"
    }
  }
}
```
"""
        parsed = parse_rubric_evaluation(response_text)
        assert parsed is not None

        eval_a = parsed["evaluations"]["Response A"]
        scores = {
            "accuracy": eval_a["accuracy"],
            "relevance": eval_a["relevance"],
            "completeness": eval_a["completeness"],
            "conciseness": eval_a["conciseness"],
            "clarity": eval_a["clarity"],
        }

        calculated = calculate_weighted_score(scores, UPDATED_RUBRIC_WEIGHTS)
        # Should match the "overall" in the JSON (or be very close)
        assert calculated == 7.8

    def test_ceiling_applied_to_parsed_scores(self):
        """Verify ceiling is applied when parsing low-accuracy evaluation."""
        response_text = """
```json
{
  "ranking": ["Response A"],
  "evaluations": {
    "Response A": {
      "accuracy": 3,
      "relevance": 9,
      "completeness": 9,
      "conciseness": 9,
      "clarity": 9,
      "overall": 6.9,
      "notes": "Factual errors despite good writing"
    }
  }
}
```
"""
        parsed = parse_rubric_evaluation(response_text)
        assert parsed is not None

        eval_a = parsed["evaluations"]["Response A"]
        scores = {
            "accuracy": eval_a["accuracy"],
            "relevance": eval_a["relevance"],
            "completeness": eval_a["completeness"],
            "conciseness": eval_a["conciseness"],
            "clarity": eval_a["clarity"],
        }

        # Model reported 6.9 but our ceiling should cap it at 4.0
        calculated = calculate_weighted_score_with_accuracy_ceiling(scores, UPDATED_RUBRIC_WEIGHTS)
        assert calculated == 4.0


class TestRubricDimensionOrder:
    """#592: rubric criteria were listed in one fixed order, always.

    ACCURACY -> RELEVANCE -> COMPLETENESS -> CONCISENESS -> CLARITY was emitted
    for every reviewer of every run, so any position preference a judge holds
    applied systematically instead of averaging out. Rubric-based judging is
    documented to show position effects tied to where a criterion sits in the
    list; the mitigation is to permute it.

    Opt-in via `evaluation.rubric.randomize_dimension_order`
    (`RUBRIC_RANDOMIZE_DIMENSION_ORDER`), default OFF.

    SCOPE: varies per council call, not per reviewer — stage 2 builds one
    prompt for all reviewers. Per-reviewer variation is #602.
    """

    def _weights(self):
        return {
            "accuracy": 0.35,
            "relevance": 0.10,
            "completeness": 0.20,
            "conciseness": 0.15,
            "clarity": 0.20,
        }

    def test_default_order_is_unchanged(self):
        """Flag off must reproduce the pre-#592 criteria order exactly."""
        from llm_council.council_stages import _rubric_dimension_order

        keys = [key for key, _title, _bullets in _rubric_dimension_order(randomize=False)]
        assert keys == ["accuracy", "relevance", "completeness", "conciseness", "clarity"]

    def test_flag_off_renders_byte_identical_criteria_block(self):
        """Golden test: the exact text the prompt carried before #592.

        Guards the refactor that moved the criteria out of the f-string and
        into data — any drift in wording, numbering, or spacing fails here.
        """
        from llm_council.council_stages import (
            _rubric_dimension_order,
            _render_rubric_criteria,
        )

        expected = """1. **ACCURACY** (35% of final score)
   - Is the information factually correct?
   - Are there any hallucinations or errors?
   - Are claims properly qualified when uncertain?

2. **RELEVANCE** (10% of final score)
   - Does it directly address the question asked?
   - Is all content pertinent to the query?
   - Does it stay on topic?

3. **COMPLETENESS** (20% of final score)
   - Does it address all aspects of the question?
   - Are important considerations included?
   - Is the answer substantive enough?

4. **CONCISENESS** (15% of final score)
   - Is every sentence adding value?
   - Does it avoid unnecessary padding, hedging, or repetition?
   - Is it appropriately brief for the question's complexity?

5. **CLARITY** (20% of final score)
   - Is it well-organized and easy to follow?
   - Is the language clear and unambiguous?
   - Would the intended audience understand it?"""

        rendered = _render_rubric_criteria(
            _rubric_dimension_order(randomize=False), self._weights()
        )
        assert rendered == expected

    def test_randomized_order_still_contains_every_dimension_once(self):
        """Permuting must not drop, duplicate, or invent a dimension."""
        from llm_council.council_stages import _rubric_dimension_order
        from llm_council.rubric import REQUIRED_DIMENSIONS

        for _ in range(25):
            keys = [k for k, _t, _b in _rubric_dimension_order(randomize=True)]
            assert sorted(keys) == sorted(REQUIRED_DIMENSIONS)
            assert len(keys) == len(set(keys))

    def test_randomized_order_actually_varies(self):
        """A shuffle that never shuffles would silently defeat the point."""
        from llm_council.council_stages import _rubric_dimension_order

        seen = {
            tuple(k for k, _t, _b in _rubric_dimension_order(randomize=True))
            for _ in range(50)
        }
        assert len(seen) > 1, "randomize=True produced one fixed order across 50 calls"

    def test_weights_follow_their_dimension_when_reordered(self):
        """A permuted list must not detach a weight from its criterion."""
        from llm_council.council_stages import (
            _rubric_dimension_order,
            _render_rubric_criteria,
        )

        weights = self._weights()
        for _ in range(15):
            dims = _rubric_dimension_order(randomize=True)
            rendered = _render_rubric_criteria(dims, weights)
            for key, title, _bullets in dims:
                pct = int(weights[key] * 100)
                assert f"**{title}** ({pct}% of final score)" in rendered

    def test_renumbering_is_sequential_after_shuffle(self):
        """Criteria stay numbered 1..5 in presentation order, not by identity."""
        from llm_council.council_stages import (
            _rubric_dimension_order,
            _render_rubric_criteria,
        )

        rendered = _render_rubric_criteria(
            _rubric_dimension_order(randomize=True), self._weights()
        )
        numbers = [line.split(".")[0] for line in rendered.splitlines() if line.startswith(("1", "2", "3", "4", "5"))]
        assert numbers == ["1", "2", "3", "4", "5"]

    def test_json_score_keys_match_criteria_order(self):
        """The answer template must present keys in the same order as the criteria."""
        from llm_council.council_stages import (
            _rubric_dimension_order,
            _render_rubric_score_keys,
        )

        dims = _rubric_dimension_order(randomize=True)
        rendered = _render_rubric_score_keys(dims)
        rendered_keys = [line.split('"')[1] for line in rendered.splitlines()]
        assert rendered_keys == [k for k, _t, _b in dims]

    def test_parser_is_order_independent(self):
        """The reason reordering is safe: scores are read by key, not position."""
        import json

        shuffled = {
            "ranking": ["Response A"],
            "evaluations": {
                "Response A": {
                    "clarity": 9,
                    "accuracy": 8,
                    "conciseness": 6,
                    "relevance": 7,
                    "completeness": 5,
                    "notes": "keys deliberately out of declaration order",
                }
            },
        }
        parsed = parse_rubric_evaluation(f"```json\n{json.dumps(shuffled)}\n```")
        assert parsed is not None
        scores = parsed["evaluations"]["Response A"]
        assert scores["accuracy"] == 8 and scores["clarity"] == 9

    def test_config_flag_defaults_off(self):
        """Byte-identical-by-default is the project convention."""
        from llm_council.unified_config import RubricConfig

        assert RubricConfig().randomize_dimension_order is False

    def test_env_var_can_enable_the_flag(self, monkeypatch):
        """The pydantic `validation_alias` alone does NOT read the environment.

        `UnifiedConfig` is a plain BaseModel, not BaseSettings — env vars are
        applied by `_apply_env_overrides`, so a flag missing from that function
        is unsettable in practice however it is declared. Caught exactly that
        way during #592: the flag existed and read False no matter what.
        """
        from llm_council.unified_config import get_config, reload_config

        monkeypatch.setenv("RUBRIC_RANDOMIZE_DIMENSION_ORDER", "true")
        reload_config()
        try:
            assert get_config().evaluation.rubric.randomize_dimension_order is True
        finally:
            monkeypatch.delenv("RUBRIC_RANDOMIZE_DIMENSION_ORDER", raising=False)
            reload_config()
