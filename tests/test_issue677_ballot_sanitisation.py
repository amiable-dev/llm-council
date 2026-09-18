"""#677 (raised by the #678 council gate): sanitise ballots at source.

Positions were derived from the raw, model-emitted ranking list. Verified
against the pre-fix code before accepting the finding:

* unknown labels **consumed positions**, so a valid label at index >= N scored
  ``borda = -1.0`` — outside the documented [0,1] range — with
  ``average_position = 5.0`` in a THREE-candidate council;
* one reviewer repeating a label three times registered ``vote_count = 3``;
* an unhashable label raised ``TypeError: unhashable type: 'list'`` at
  ``label in label_to_model`` — the #657 crash class, already guarded in
  ``detect_score_rank_mismatch`` but not here or in the shadow-vote block.

Semantically wrong positions reaching CSS is precisely what #677 set out to
stop, so the ballot is sanitised where it is read rather than patched
downstream.
"""

import pytest

from llm_council.council_rankings import (
    calculate_aggregate_rankings,
    rankings_to_position_tuples,
)

LABELS = ["Response A", "Response B", "Response C"]


def _l2m():
    return {lab: {"model": f"m{i + 1}", "display_index": i} for i, lab in enumerate(LABELS)}


def _ballot(reviewer, ranking):
    return {"model": reviewer, "ranking": "", "parsed_ranking": {"ranking": ranking}}


def _agg(reviewer, ranking, **kw):
    return calculate_aggregate_rankings([_ballot(reviewer, ranking)], _l2m(), **kw)


class TestBallotSanitisation:
    def test_unknown_labels_do_not_consume_positions(self):
        agg = _agg("m1", ["Response Z", "Response Y", "Response X", "Response W", "Response C"])
        c = next(r for r in agg if r["model"] == "m3")
        assert c["borda_score"] is not None
        assert 0.0 <= c["borda_score"] <= 1.0, "borda must stay in the documented range"
        assert c["average_position"] == 1.0, "the only valid vote is a first-place vote"

    def test_borda_never_leaves_the_unit_interval(self):
        agg = _agg("m1", ["junk"] * 10 + ["Response B", "Response C"])
        for r in agg:
            if r["borda_score"] is not None:
                assert 0.0 <= r["borda_score"] <= 1.0, r

    def test_duplicate_labels_count_once(self):
        agg = _agg("m2", ["Response A", "Response A", "Response A"])
        m1 = next(r for r in agg if r["model"] == "m1")
        assert m1["vote_count"] == 1, "one reviewer is one vote"
        assert m1["average_position"] == 1.0

    def test_unhashable_label_does_not_raise(self):
        agg = _agg("m2", [["nested"], {"a": 1}, "Response A"])
        m1 = next(r for r in agg if r["model"] == "m1")
        assert m1["average_position"] == 1.0

    def test_unhashable_label_in_the_shadow_vote_path_does_not_raise(self):
        from llm_council.voting import VotingAuthority

        agg = _agg(
            "m2",
            [["nested"], "Response A"],
            voting_authorities={"m2": VotingAuthority.ADVISORY},
            return_shadow_votes=True,
        )
        assert agg  # completed rather than raising


class TestHelperRejectsNonsensePositions:
    """NaN/inf/0/negative all passed the numeric gate. NaN is worse than the
    TypeError being fixed: it silently corrupts CSS's ordering instead of
    reporting the signal as unavailable."""

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), 0, -3.0])
    def test_non_finite_and_out_of_range_positions_are_dropped(self, bad):
        out = rankings_to_position_tuples(
            [
                {"model": "m1", "average_position": 1.0},
                {"model": "m2", "average_position": bad},
            ]
        )
        assert out == [("m1", 1.0)]

    def test_truthy_non_iterable_does_not_raise(self):
        """The docstring promises a total function; `x or []` raised on 42."""
        assert rankings_to_position_tuples(42) == []
        assert rankings_to_position_tuples(object()) == []


class TestSortKeyDistinguishesZeroFromUnranked:
    """`-(x["borda_score"] or -999)` treated a legitimate last-place 0.0 as
    missing, sorting a genuinely ranked candidate down among the unranked."""

    def test_zero_borda_outranks_unranked(self):
        # m3 is ranked (last) by both reviewers; nobody ranks m2's response.
        ballots = [_ballot(r, ["Response A", "Response C"]) for r in ("m2", "m3")]
        agg = calculate_aggregate_rankings(ballots, _l2m())
        order = [r["model"] for r in agg]
        assert order.index("m3") < order.index("m2"), (
            "a ranked-last candidate must outrank one nobody ranked"
        )
