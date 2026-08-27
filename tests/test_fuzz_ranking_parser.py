"""Hypothesis-based fuzz/property tests for the Stage 2 ranking parser (#657).

`parse_ranking_from_text` and `detect_score_rank_mismatch` consume raw model
output — adversarial-by-construction input (a reviewer model can emit
anything, including deliberately or accidentally malformed structures) — and
run unguarded in the main Stage 2 results-aggregation loop
(`council_stages.py`), so a crash here fails the whole council run, not just
one reviewer. This is the project's dynamic-analysis coverage (CII Best
Practices `dynamic_analysis`): both functions must never raise on arbitrary
input, only ever return their documented shape.
"""

import json

from hypothesis import given, settings, strategies as st

from llm_council.council_rankings import detect_score_rank_mismatch, parse_ranking_from_text

json_scalar = (
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=50)
)
json_value = st.recursive(
    json_scalar,
    lambda children: st.lists(children, max_size=5) | st.dictionaries(st.text(max_size=20), children, max_size=5),
    max_leaves=20,
)


@given(st.text())
@settings(max_examples=300)
def test_parse_ranking_from_text_never_crashes_on_arbitrary_text(text):
    result = parse_ranking_from_text(text)
    assert isinstance(result, dict)
    assert "ranking" in result
    assert "scores" in result


@given(json_value)
@settings(max_examples=300)
def test_parse_ranking_from_text_never_crashes_on_malformed_json_shapes(obj):
    """A markdown-fenced JSON block whose 'ranking'/'scores' shape is arbitrary."""
    text = f"```json\n{json.dumps(obj)}\n```"
    result = parse_ranking_from_text(text)
    assert isinstance(result, dict)
    assert "ranking" in result
    assert "scores" in result


@given(st.lists(json_value, max_size=10), st.dictionaries(st.text(max_size=20), json_value, max_size=10))
@settings(max_examples=300)
def test_detect_score_rank_mismatch_never_crashes_on_arbitrary_shapes(ranking, scores):
    result = detect_score_rank_mismatch(ranking, scores)
    assert isinstance(result, bool)


def test_regression_non_string_ranking_element_does_not_crash():
    """Found by the fuzz suite above: a ranking entry that isn't a string
    (e.g. a nested object) made `label in scores` raise TypeError:
    unhashable type, since JSON parsing gives no element-type guarantee.
    """
    text = '```json\n{"ranking": [{"a": 1}, "Response B"], "scores": {"Response B": 5}}\n```'
    result = parse_ranking_from_text(text)
    assert result["ranking"] == [{"a": 1}, "Response B"]
    assert result["scores"] == {"Response B": 5}


def test_regression_unhashable_ranking_element_direct():
    assert detect_score_rank_mismatch([["a", "list"], "Response A"], {"Response A": 1}) is False


def test_regression_non_dict_fenced_json_does_not_crash():
    """Found by the fuzz suite above: a fenced JSON block can be any valid
    JSON value, not just an object (e.g. `null`, a bare array/number) —
    `parsed.get(...)` on a non-dict raised AttributeError.
    """
    for body in ("null", "42", '"just a string"', "[1, 2, 3]"):
        result = parse_ranking_from_text(f"```json\n{body}\n```")
        assert result == {"ranking": [], "scores": {}}
