"""Tests for ADR-042 _budget_evidence helper.

TDD Red Phase: These tests should fail until _budget_evidence is implemented
in src/llm_council/verification/api.py.

Covers spec §14.2 (Budgeting).
"""

import pytest

from llm_council.verification.api import (
    BlockingEvidenceTooLarge,
    EvidenceItem,
    MAX_EVIDENCE_CHARS_RATIO,
    TIER_MAX_CHARS,
    _budget_evidence,
)


class TestBudgeter:
    """Whole-item budgeting with deterministic ordering."""

    def test_empty_returns_empty(self):
        kept, warnings = _budget_evidence(None, "balanced")
        assert kept == []
        assert warnings == []

    def test_explicit_empty_list(self):
        kept, warnings = _budget_evidence([], "balanced")
        assert kept == []
        assert warnings == []

    def test_under_budget_keeps_all(self):
        # balanced budget = 30K * 0.20 = 6K. Two 1K items = 2K, well under.
        items = [
            EvidenceItem(source="a@1", content="x" * 1000),
            EvidenceItem(source="b@1", content="y" * 1000),
        ]
        kept, warnings = _budget_evidence(items, "balanced")
        assert len(kept) == 2
        assert warnings == []

    def test_drops_overflow_items_whole(self):
        # balanced budget = 6K. Three 3K items: 1st fits (3K used),
        # 2nd fits (6K used), 3rd drops.
        items = [EvidenceItem(source=f"src{i}@1", content="x" * 3000) for i in range(3)]
        kept, warnings = _budget_evidence(items, "balanced")
        assert len(kept) == 2
        assert len(warnings) == 1
        assert warnings[0].reason == "budget_overflow_dropped"
        assert warnings[0].chars_kept == 0
        assert warnings[0].chars_attempted == 3000

    def test_blocking_oversized_raises_too_large(self):
        # balanced budget = 6K; one blocking item is 10K → raise.
        items = [
            EvidenceItem(source="blk@1", content="x" * 10000, strength="blocking"),
        ]
        with pytest.raises(BlockingEvidenceTooLarge) as exc:
            _budget_evidence(items, "balanced")
        assert exc.value.index == 0
        assert exc.value.source == "blk@1"
        assert exc.value.chars == 10000
        assert exc.value.budget == 6000

    def test_blocking_oversized_uses_caller_index(self):
        # If the oversized blocking item is at index 2, the error reports 2,
        # not the post-sort position.
        items = [
            EvidenceItem(source="a@1", content="x"),
            EvidenceItem(source="b@1", content="y"),
            EvidenceItem(source="blk@1", content="x" * 10000, strength="blocking"),
        ]
        with pytest.raises(BlockingEvidenceTooLarge) as exc:
            _budget_evidence(items, "balanced")
        assert exc.value.index == 2

    def test_blocking_first_ordering(self):
        # Budget = 6K. Two items: informational 5K (alphabetically first
        # source), blocking 5K. Blocking must be kept; informational dropped.
        items = [
            EvidenceItem(source="a-info@1", content="x" * 5000, strength="informational"),
            EvidenceItem(source="z-block@1", content="y" * 5000, strength="blocking"),
        ]
        kept, warnings = _budget_evidence(items, "balanced")
        assert len(kept) == 1
        kept_req_idx, kept_item = kept[0]
        assert kept_item.strength == "blocking"
        assert kept_req_idx == 1
        assert len(warnings) == 1
        assert warnings[0].source == "a-info@1"

    def test_deterministic_within_strength(self):
        # Three informational items at 2K each (total 6K = budget).
        # Order in input is z, a, m; sort should yield a, m, z.
        items = [
            EvidenceItem(source="z@1", content="x" * 2000),
            EvidenceItem(source="a@1", content="y" * 2000),
            EvidenceItem(source="m@1", content="z" * 2000),
        ]
        kept, _ = _budget_evidence(items, "balanced")
        sources_in_order = [item.source for _, item in kept]
        assert sources_in_order == ["a@1", "m@1", "z@1"]

    def test_evidence_id_breaks_source_ties(self):
        # Same source, different evidence_id — id is the tiebreaker.
        items = [
            EvidenceItem(source="s@1", content="x" * 2000, evidence_id="z-id"),
            EvidenceItem(source="s@1", content="y" * 2000, evidence_id="a-id"),
            EvidenceItem(source="s@1", content="z" * 2000, evidence_id="m-id"),
        ]
        kept, _ = _budget_evidence(items, "balanced")
        ids_in_order = [item.evidence_id for _, item in kept]
        assert ids_in_order == ["a-id", "m-id", "z-id"]

    def test_auto_id_fallback_used_in_ordering(self):
        # No evidence_id → auto-<request_index>. The fallback string is what
        # gets compared, so request_index order is preserved within
        # same-source ties.
        items = [
            EvidenceItem(source="s@1", content="x" * 1000),  # auto-0
            EvidenceItem(source="s@1", content="y" * 1000),  # auto-1
            EvidenceItem(source="s@1", content="z" * 1000),  # auto-2
        ]
        kept, _ = _budget_evidence(items, "balanced")
        request_indices = [req_idx for req_idx, _ in kept]
        assert request_indices == [0, 1, 2]

    @pytest.mark.parametrize(
        "tier,expected_budget",
        [
            ("quick", 1500),
            ("balanced", 6000),
            ("high", 10000),
            ("reasoning", 10000),
        ],
    )
    def test_per_tier_ratio(self, tier, expected_budget):
        # Fill exactly the budget; assert all kept, zero warnings.
        items = [EvidenceItem(source="t@1", content="x" * expected_budget)]
        kept, warnings = _budget_evidence(items, tier)
        assert len(kept) == 1
        assert warnings == []

    def test_unknown_tier_uses_default_ratio(self):
        # Defaults to 0.20 ratio and TIER_MAX_CHARS default of 50K → 10K budget.
        items = [EvidenceItem(source="t@1", content="x" * 10000)]
        kept, _ = _budget_evidence(items, "unknown-tier-xyz")
        assert len(kept) == 1

    def test_max_evidence_chars_ratio_per_tier(self):
        # Sanity check the constants against the spec.
        assert MAX_EVIDENCE_CHARS_RATIO["quick"] == 0.10
        assert MAX_EVIDENCE_CHARS_RATIO["balanced"] == 0.20
        assert MAX_EVIDENCE_CHARS_RATIO["high"] == 0.20
        assert MAX_EVIDENCE_CHARS_RATIO["reasoning"] == 0.20

    def test_warning_carries_request_index(self):
        # Drop the third item (index 2).
        items = [EvidenceItem(source=f"src{i}@1", content="x" * 3000) for i in range(3)]
        _, warnings = _budget_evidence(items, "balanced")
        assert len(warnings) == 1
        assert warnings[0].request_index == 2
