"""ADR-047 P4: reviewer-agreement decomposition, report-only (#416).

Do reviewers converge because the work is good, or because of shared
position effects? Renders from the existing ADR-018 store; never gates.
"""

from llm_council.bias_amplification import (
    amplification_report,
    format_amplification_report,
    session_agreement_decomposition,
)
from llm_council.bias_persistence import BiasMetricRecord


def _rec(session, reviewer, model, position, score):
    return BiasMetricRecord(
        session_id=session,
        reviewer_id=reviewer,
        model_id=model,
        position=position,
        score_value=score,
    )


def _quality_convergence_session(sid="s-quality"):
    # All reviewers agree model B is best regardless of its position.
    rows = []
    for reviewer in ("r1", "r2", "r3"):
        rows += [
            _rec(sid, reviewer, "A", 0, 5.0),
            _rec(sid, reviewer, "B", 1, 9.0),
            _rec(sid, reviewer, "C", 2, 4.0),
        ]
    return rows


def _positional_amplification_session(sid="s-position"):
    # All reviewers score strictly by display position: earlier = better.
    rows = []
    for reviewer in ("r1", "r2", "r3"):
        rows += [
            _rec(sid, reviewer, "A", 0, 9.0),
            _rec(sid, reviewer, "B", 1, 7.0),
            _rec(sid, reviewer, "C", 2, 5.0),
        ]
    return rows


def _disagreement_session(sid="s-noise"):
    rows = [
        _rec(sid, "r1", "A", 0, 9.0),
        _rec(sid, "r1", "B", 1, 4.0),
        _rec(sid, "r2", "A", 0, 3.0),
        _rec(sid, "r2", "B", 1, 8.0),
    ]
    return rows


class TestDecomposition:
    def test_quality_convergence_not_flagged(self):
        sessions = session_agreement_decomposition(_quality_convergence_session())
        assert len(sessions) == 1
        s = sessions[0]
        assert s.agreement_index > 0.7  # reviewers converge
        assert abs(s.position_alignment) < 0.5  # ...but not along position
        assert s.amplification_suspect is False

    def test_positional_amplification_flagged(self):
        sessions = session_agreement_decomposition(_positional_amplification_session())
        s = sessions[0]
        assert s.agreement_index > 0.7
        assert s.position_alignment > 0.5  # consensus tracks display order
        assert s.amplification_suspect is True

    def test_disagreement_not_flagged(self):
        sessions = session_agreement_decomposition(_disagreement_session())
        s = sessions[0]
        assert s.agreement_index < 0.7
        assert s.amplification_suspect is False

    def test_single_reviewer_sessions_skipped(self):
        rows = [_rec("s1", "r1", "A", 0, 9.0), _rec("s1", "r1", "B", 1, 4.0)]
        assert session_agreement_decomposition(rows) == []


class TestReport:
    def test_aggregates(self):
        rows = (
            _quality_convergence_session()
            + _positional_amplification_session()
            + _disagreement_session()
        )
        report = amplification_report(rows)
        assert report["sessions_analyzed"] == 3
        assert report["high_agreement_sessions"] == 2
        assert report["amplification_suspects"] == 1
        assert 0 <= report["amplification_rate_among_agreement"] <= 1
        assert report["report_only"] is True

    def test_render_contains_verdict_line(self):
        report = amplification_report(_positional_amplification_session())
        text = format_amplification_report(report)
        assert "report-only" in text.lower()
        assert "amplification" in text.lower()

    def test_empty_store(self):
        report = amplification_report([])
        assert report["sessions_analyzed"] == 0
        assert "insufficient" in format_amplification_report(report).lower()


class TestNoGatingSideEffects:
    def test_pure_analysis_no_writes(self, tmp_path, monkeypatch):
        # Report-only invariant: analysis performs no filesystem writes.
        monkeypatch.chdir(tmp_path)
        rows = _positional_amplification_session()
        amplification_report(rows)
        session_agreement_decomposition(rows)
        assert list(tmp_path.iterdir()) == []  # nothing written anywhere


class TestCouncilRound1:
    def test_positions_averaged_across_reviewers(self):
        # #437 r1: ADR-017 randomization can show the SAME model at different
        # positions per reviewer — last-write-wins dropped that information.
        # A model seen early by one reviewer and late by another has mean
        # position; perfectly counterbalanced ordering => no alignment signal.
        rows = [
            _rec("s-cb", "r1", "A", 0, 9.0),
            _rec("s-cb", "r1", "B", 1, 5.0),
            _rec("s-cb", "r2", "A", 1, 9.0),  # A shown late to r2
            _rec("s-cb", "r2", "B", 0, 5.0),  # B shown early to r2
        ]
        s = session_agreement_decomposition(rows)[0]
        # Counterbalanced positions average out: alignment must be ~0, and
        # the high agreement must NOT be flagged as positional.
        assert abs(s.position_alignment) < 0.01
        assert s.amplification_suspect is False


class TestPositionAlignmentUsesDisplayOrder:
    """#611: the amplification signal was inverted by the position defect.

    `position_alignment` correlates `-position` against consensus score to
    detect "agreement that tracks DISPLAY order". While `position` held the
    reviewer's ranking index instead, a session where reviewers agreed on
    favouring the LAST-displayed model produced a strongly POSITIVE alignment
    and flagged `amplification_suspect` — the exact opposite of the truth.
    """

    def test_agreeing_on_the_last_displayed_model_is_not_a_suspect(self):
        from llm_council.bias_persistence import (
            create_bias_records_from_session,
            ConsentLevel,
        )
        from llm_council.bias_amplification import session_agreement_decomposition

        label_to_model = {
            "Response A": {"model": "m/alpha", "display_index": 0},
            "Response B": {"model": "m/beta", "display_index": 1},
            "Response C": {"model": "m/gamma", "display_index": 2},
        }
        stage1 = [
            {"model": "m/alpha", "response": "a"},
            {"model": "m/beta", "response": "b"},
            {"model": "m/gamma", "response": "c"},
        ]
        # Both reviewers strongly agree — and both favour gamma, shown LAST.
        # Display order cannot explain this agreement.
        stage2 = [
            {
                "model": f"rev/{i}",
                "parsed_ranking": {
                    "ranking": ["Response C", "Response B", "Response A"],
                    "scores": {
                        "Response A": 4.0 + i * 0.5,
                        "Response B": 6.0 + i * 0.5,
                        "Response C": 9.0 + i * 0.5,
                    },
                },
            }
            for i in (1, 2)
        ]

        records = create_bias_records_from_session(
            session_id="s1",
            stage1_results=stage1,
            stage2_results=stage2,
            label_to_model=label_to_model,
            consent_level=ConsentLevel.LOCAL_ONLY,
        )
        decomposition = session_agreement_decomposition(records)[0]

        assert decomposition.agreement_index > 0.8, "sanity: reviewers do agree here"
        assert decomposition.position_alignment < 0, (
            "the favoured model was displayed LAST, so alignment must be "
            f"negative; got {decomposition.position_alignment} — position is "
            "probably holding the ranking index again (#611)"
        )
        assert decomposition.amplification_suspect is False, (
            "high agreement that does NOT track display order is not an "
            "amplification suspect"
        )

    def test_pre_fix_records_are_excluded_from_position_analysis(self):
        """#611/#613: records written before the fix hold a different quantity.

        Bumping `schema_version` only helps if a reader acts on it. Pooled
        cross-session analysis (ADR-018) must not mix ranking indices from
        1.1.0 records with display indices from 1.2.0 ones under the same
        field name.
        """
        from llm_council.bias_persistence import BiasMetricRecord
        from llm_council.bias_amplification import session_agreement_decomposition

        def rec(schema, reviewer, model, position, score):
            return BiasMetricRecord(
                schema_version=schema,
                session_id="legacy",
                reviewer_id=reviewer,
                model_id=model,
                position=position,
                score_value=score,
            )

        legacy = [
            rec("1.1.0", "rev/1", "m/a", 0, 9.0),
            rec("1.1.0", "rev/1", "m/b", 1, 5.0),
            rec("1.1.0", "rev/2", "m/a", 0, 9.5),
            rec("1.1.0", "rev/2", "m/b", 1, 4.5),
        ]
        assert session_agreement_decomposition(legacy) == [], (
            "pre-1.2.0 records carry ranking indices under `position` and must "
            "not be analysed as display order"
        )
