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
