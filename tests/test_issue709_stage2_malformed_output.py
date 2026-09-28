"""#709, #680, #679 — stage 2 must survive malformed reviewer output.

All three are the same shape: model output is untrusted, and a value that is
present but wrong (a `None`, a bool, a NaN) walked past a default that only
fires for an ABSENT key.

* #709 — a provider sent `content: null`. `openrouter.query_model` passes it
  through as `"content": None`; stage 2 read it with `.get("content", "")`,
  whose default does not apply to a stored None, and `parse_ranking_from_text`
  called `.lower()` on it. Observed live on 2026-09-28: a verify whose stage 1
  had completed with all four models died with "'NoneType' object has no
  attribute 'lower'", reported as UNCLEAR with no reason.
* #680 — `ranking.get("parsed_ranking", {})` returns a stored None, and the
  next `.get` raises. The same expression appears at six sites.
* #679 — raw scores reached the aggregate's sort key unguarded: a bool scored
  0.1, NaN poisoned the ordering, and nothing clamped to the documented [0, 1].
"""

import ast
import asyncio
import math
import pathlib
from unittest.mock import patch

import pytest

from llm_council.council_rankings import calculate_aggregate_rankings, parse_ranking_from_text

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "llm_council"

LABELS = {
    "Response A": {"model": "a/one", "display_index": 0},
    "Response B": {"model": "b/two", "display_index": 1},
}


class TestAReviewerThatReturnedNothing:
    def test_the_parser_treats_none_as_an_abstention(self):
        parsed = parse_ranking_from_text(None)
        assert parsed["ranking"] == []
        assert parsed.get("abstained") is True

    @pytest.mark.parametrize("incremental", [False, True])
    def test_stage_2_completes_when_a_provider_sends_content_null(self, incremental):
        """End to end through stage 2, on both the batch and incremental paths.
        A parser that tolerates None proves nothing if a caller still crashes."""
        from llm_council import council_stages

        good = "FINAL RANKING:\n1. Response A\n2. Response B"
        stage1 = [
            {"model": "a/one", "response": "first answer"},
            {"model": "b/two", "response": "second answer"},
        ]
        replies = {
            "a/one": {"content": None, "usage": {}},
            "b/two": {"content": good, "usage": {}},
        }

        async def parallel(models, *_a, **_k):
            return {m: replies[m] for m in models}

        async def single(model, *_a, **_k):
            return replies[model]

        events = []

        async def on_review_event(kind, payload):
            events.append(payload)

        with (
            patch.object(council_stages, "query_models_parallel", parallel),
            patch.object(council_stages, "query_model", single),
        ):
            results, _labels, _usage = asyncio.run(
                council_stages.stage2_collect_rankings(
                    "q",
                    stage1,
                    timeout=5,
                    models=["a/one", "b/two"],
                    on_review_event=on_review_event if incremental else None,
                )
            )
        by_model = {r["model"]: r for r in results}
        assert by_model["b/two"]["parsed_ranking"]["ranking"]
        assert by_model["a/one"]["parsed_ranking"]["ranking"] == []
        # The null reply is an explicit abstention, not a silent empty ballot.
        assert by_model["a/one"]["parsed_ranking"].get("abstained") is True
        if incremental:
            # The review-event path parsed both replies, the null one included.
            reviewers = {e["reviewer"]: e for e in events}
            assert set(reviewers) == {"a/one", "b/two"}
            assert reviewers["a/one"]["parse_ok"] is False
            assert reviewers["b/two"]["parse_ok"] is True


class TestAStoredNoneParsedRanking:
    def test_the_aggregate_skips_it_and_counts_the_rest(self):
        # A third-party reviewer, so self-vote exclusion does not drop the vote.
        stage2 = [
            {"model": "a/one", "parsed_ranking": None},
            {"model": "c/three", "parsed_ranking": {"ranking": ["Response B", "Response A"]}},
        ]
        aggregate = calculate_aggregate_rankings(stage2, LABELS)
        assert [row["model"] for row in aggregate][:1] == ["b/two"]

    @pytest.mark.parametrize("scores", [None, ["Response A"], "9"])
    def test_non_dict_scores_do_not_raise(self, scores):
        stage2 = [{"model": "a/one", "parsed_ranking": {"ranking": ["Response A"], "scores": scores}}]
        calculate_aggregate_rankings(stage2, LABELS)

    def test_no_source_file_reads_parsed_ranking_with_a_dict_default(self):
        """`.get("parsed_ranking", {})` is the trap: it returns a stored None.
        Every site goes through `parsed_ranking_of` instead."""
        offenders = []
        for path in SRC.rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and len(node.args) == 2
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "parsed_ranking"
                    and isinstance(node.args[1], ast.Dict)
                ):
                    offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")
        assert not offenders, f"read parsed_ranking via parsed_ranking_of(): {offenders}"

    @pytest.mark.parametrize(
        "call",
        [
            lambda s: __import__("llm_council.dissent", fromlist=["x"]).extract_dissent_from_stage2(s),
            lambda s: __import__("llm_council.dissent", fromlist=["x"]).extract_outlier_info(s),
            lambda s: __import__("llm_council.bias_audit", fromlist=["x"]).extract_scores_from_stage2(
                s, LABELS
            ),
            lambda s: __import__(
                "llm_council.verification.verdict_extractor", fromlist=["x"]
            ).extract_rubric_scores_from_rankings(s),
        ],
    )
    def test_every_other_reader_survives_it(self, call):
        call([{"model": "a/one", "parsed_ranking": None}])


class TestRawScoresAreSanitised:
    @pytest.mark.parametrize("bad", [True, False, float("nan"), float("inf"), float("-inf"), "junk"])
    def test_a_bad_score_does_not_reach_the_aggregate(self, bad):
        stage2 = [
            {
                "model": "b/two",
                "parsed_ranking": {"ranking": ["Response A", "Response B"], "scores": {"Response A": bad}},
            }
        ]
        for row in calculate_aggregate_rankings(stage2, LABELS):
            score = row.get("average_score")
            assert score is None or (math.isfinite(score) and 0.0 <= score <= 1.0)

    def test_an_out_of_range_score_is_clamped(self):
        stage2 = [
            {
                "model": "b/two",
                "parsed_ranking": {"ranking": ["Response A", "Response B"], "scores": {"Response A": 15}},
            }
        ]
        row = next(r for r in calculate_aggregate_rankings(stage2, LABELS) if r["model"] == "a/one")
        assert row["average_score"] == 1.0

    def test_a_numeric_string_is_accepted_like_elsewhere(self):
        stage2 = [
            {
                "model": "b/two",
                "parsed_ranking": {"ranking": ["Response A", "Response B"], "scores": {"Response A": "8"}},
            }
        ]
        row = next(r for r in calculate_aggregate_rankings(stage2, LABELS) if r["model"] == "a/one")
        assert row["average_score"] == pytest.approx(0.8)


class TestTheDissentSpreadGateStillCounts:
    """The #680 rewrite of dissent's spread check briefly mis-indented its
    guard, so `all_scores` stayed empty and the spread gate never fired. The
    existing spread test did not notice: its fixture has no outlier, so it
    returns None before the gate. This one has a real outlier."""

    @staticmethod
    def _stage2():
        scores = [7, 7, 7, 7, 4]
        stage2 = [
            {"model": f"r{i}", "parsed_ranking": {"ranking": ["Response A"], "scores": {"Response A": s}}}
            for i, s in enumerate(scores)
        ]
        stage2.append({"model": "broken", "parsed_ranking": None})
        return stage2

    def test_the_outlier_is_detected_without_a_spread_requirement(self):
        from llm_council.dissent import extract_dissent_from_stage2

        assert extract_dissent_from_stage2(self._stage2(), min_borda_spread=0.0)

    def test_a_spread_below_the_minimum_suppresses_it(self):
        from llm_council.dissent import extract_dissent_from_stage2

        assert extract_dissent_from_stage2(self._stage2(), min_borda_spread=3.5) is None


def test_the_parser_fuzzer_bundles_the_package_data():
    """The ClusterFuzzLite binary is built with PyInstaller, which bundles
    code but not package data. Since #690, importing llm_council reads
    models/default_pools.yaml, so a fuzzer without the data dies at startup
    and fails every parser PR as "BAD BUILD" (seen on #712)."""
    build = (SRC.parent.parent / ".clusterfuzzlite" / "build.sh").read_text()
    assert "--collect-data llm_council" in build


class TestGateRound1:
    """Council gate on #712, round 1: dissent was routed through
    parsed_ranking_of but its per-score values were still trusted."""

    @pytest.mark.parametrize(
        "bad_scores",
        [
            "9",
            ["Response A"],
            {"Response A": "N/A"},
            {"Response A": float("nan")},
            {"Response A": True},
            {"Response A": "7"},
        ],
    )
    def test_dissent_survives_any_score_shape(self, bad_scores):
        from llm_council.dissent import (
            extract_dissent_from_stage2,
            extract_outlier_info,
            identify_outlier_reviewers,
        )

        stage2 = [
            {"model": f"r{i}", "parsed_ranking": {"scores": {"Response A": s}}}
            for i, s in enumerate([7, 7, 7, 4])
        ]
        stage2.append({"model": "odd", "parsed_ranking": {"scores": bad_scores}})
        extract_outlier_info(stage2)
        extract_dissent_from_stage2(stage2, min_borda_spread=1.0)
        identify_outlier_reviewers({"odd": bad_scores, "r0": {"Response A": 7}})

    def test_a_numeric_string_score_counts_like_elsewhere(self):
        from llm_council.dissent import _numeric_scores

        assert _numeric_scores({"A": "7", "B": True, "C": float("inf"), "D": 5}) == {
            "A": 7.0,
            "D": 5.0,
        }

    @pytest.mark.parametrize("raw", ["nan", "inf", "-inf", float("nan"), 10**400])
    def test_coerce_score_sorts_every_non_finite_value_last(self, raw):
        from llm_council.council_rankings import _coerce_score

        assert _coerce_score(raw) == float("-inf")

    @pytest.mark.parametrize("text", ["", "   \n"])
    def test_an_empty_reply_is_an_abstention(self, text):
        assert parse_ranking_from_text(text).get("abstained") is True
