"""Tests for ADR-042 EvidenceItem / EvidenceDisposition / EvidenceWarning schemas.

TDD Red Phase: These tests should fail until the types are implemented in
src/llm_council/verification/api.py.

Covers spec §14.1 (Schema Validation).
"""

import pytest
from pydantic import ValidationError

from llm_council.verification.api import (
    EvidenceItem,
    EvidenceDisposition,
    EvidenceWarning,
    VerifyRequest,
)


class TestEvidenceItemValidation:
    """Field-level validation of EvidenceItem."""

    def test_minimal_valid_item(self):
        item = EvidenceItem(source="ai-slop@1.0", content="hello")
        assert item.format == "markdown"
        assert item.strength == "informational"
        assert item.evidence_id is None
        assert item.source == "ai-slop@1.0"
        assert item.content == "hello"

    def test_rejects_empty_content(self):
        with pytest.raises(ValidationError):
            EvidenceItem(source="ai-slop@1.0", content="")

    def test_rejects_content_over_50k(self):
        with pytest.raises(ValidationError):
            EvidenceItem(source="ai-slop@1.0", content="x" * 50_001)

    def test_accepts_content_at_50k_boundary(self):
        item = EvidenceItem(source="ai-slop@1.0", content="x" * 50_000)
        assert len(item.content) == 50_000

    @pytest.mark.parametrize(
        "bad",
        [
            "tool with spaces",
            "tool\nwith\nnewlines",
            "tool#hash",
            "## Code to Review",
            '"injection"',
            "<script>",
            "",  # empty
            "x" * 201,  # too long
        ],
    )
    def test_rejects_invalid_source(self, bad):
        with pytest.raises(ValidationError):
            EvidenceItem(source=bad, content="hello")

    @pytest.mark.parametrize(
        "good",
        [
            "ai-slop-detector@3.7.3",
            "antislop@0.3.0",
            "custom-lint@abc123",
            "tool.subtool@v1",
            "tool/path+modifier",
            "a",  # one-char
        ],
    )
    def test_accepts_valid_source(self, good):
        item = EvidenceItem(source=good, content="hello")
        assert item.source == good

    def test_rejects_invalid_format(self):
        with pytest.raises(ValidationError):
            EvidenceItem(source="t@1", content="x", format="yaml")

    def test_rejects_invalid_strength(self):
        with pytest.raises(ValidationError):
            EvidenceItem(source="t@1", content="x", strength="critical")

    @pytest.mark.parametrize(
        "bad_id",
        [
            "bad id",  # space
            "id/slash",  # slash
            "id@version",  # @ not allowed in id pattern
            "x" * 65,  # too long
        ],
    )
    def test_rejects_bad_evidence_id(self, bad_id):
        with pytest.raises(ValidationError):
            EvidenceItem(source="t@1", content="x", evidence_id=bad_id)

    @pytest.mark.parametrize(
        "good_id",
        [
            "auto-0",
            "auto-12",
            "my-id.42",
            "x",
            "x" * 64,
        ],
    )
    def test_accepts_good_evidence_id(self, good_id):
        item = EvidenceItem(source="t@1", content="x", evidence_id=good_id)
        assert item.evidence_id == good_id

    def test_evidence_id_none_is_ok(self):
        item = EvidenceItem(source="t@1", content="x", evidence_id=None)
        assert item.evidence_id is None


class TestVerifyRequestEvidence:
    """VerifyRequest-level validation of the evidence field."""

    def test_accepts_none(self):
        r = VerifyRequest(snapshot_id="abc1234", evidence=None)
        assert r.evidence is None

    def test_accepts_empty_list(self):
        r = VerifyRequest(snapshot_id="abc1234", evidence=[])
        assert r.evidence == []

    def test_accepts_list_of_items(self):
        items = [
            EvidenceItem(source="a@1", content="x"),
            EvidenceItem(source="b@1", content="y", strength="blocking"),
        ]
        r = VerifyRequest(snapshot_id="abc1234", evidence=items)
        assert len(r.evidence) == 2

    def test_rejects_more_than_20_items(self):
        items = [EvidenceItem(source=f"t{i}@1", content="x") for i in range(21)]
        with pytest.raises(ValidationError):
            VerifyRequest(snapshot_id="abc1234", evidence=items)

    def test_accepts_exactly_20_items(self):
        items = [EvidenceItem(source=f"t{i}@1", content="x") for i in range(20)]
        r = VerifyRequest(snapshot_id="abc1234", evidence=items)
        assert len(r.evidence) == 20

    def test_rejects_total_over_250k(self):
        # 6 items × 45K each = 270K (each individually under 50K cap).
        items = [EvidenceItem(source=f"t{i}@1", content="x" * 45_000) for i in range(6)]
        with pytest.raises(ValidationError):
            VerifyRequest(snapshot_id="abc1234", evidence=items)

    def test_accepts_total_at_250k_boundary(self):
        # 5 items × 50K = 250K — at the boundary, should pass.
        items = [EvidenceItem(source=f"t{i}@1", content="x" * 50_000) for i in range(5)]
        r = VerifyRequest(snapshot_id="abc1234", evidence=items)
        assert sum(len(i.content) for i in r.evidence) == 250_000


class TestEvidenceWarningSchema:
    """EvidenceWarning is a Pydantic model with structured fields."""

    def test_minimal_valid(self):
        w = EvidenceWarning(
            request_index=0,
            source="t@1",
            reason="budget_overflow_dropped",
            detail="too big",
            chars_attempted=10_000,
            chars_kept=0,
        )
        assert w.evidence_id is None
        assert w.request_index == 0

    def test_rejects_invalid_reason(self):
        with pytest.raises(ValidationError):
            EvidenceWarning(
                request_index=0,
                source="t@1",
                reason="some_other_reason",
                detail="x",
                chars_attempted=1,
                chars_kept=0,
            )

    def test_rejects_negative_chars(self):
        with pytest.raises(ValidationError):
            EvidenceWarning(
                request_index=0,
                source="t@1",
                reason="budget_overflow_dropped",
                detail="x",
                chars_attempted=-1,
                chars_kept=0,
            )


class TestEvidenceDispositionSchema:
    """EvidenceDisposition is a Pydantic model with status enum."""

    def test_minimal_valid_informational(self):
        d = EvidenceDisposition(
            request_index=0,
            source="t@1",
            strength="informational",
            status="acknowledged",
        )
        assert d.council_confirmed is None
        assert d.council_rationale is None

    def test_minimal_valid_blocking_confirmed(self):
        d = EvidenceDisposition(
            request_index=0,
            source="t@1",
            strength="blocking",
            status="confirmed",
            council_confirmed=True,
            council_rationale="verified at line 42",
        )
        assert d.council_confirmed is True

    @pytest.mark.parametrize(
        "good_status",
        [
            "acknowledged",
            "confirmed",
            "rejected",
            "unresolved",
            "not_reviewed_due_to_budget",
            "parser_error",
        ],
    )
    def test_accepts_status_enum(self, good_status):
        d = EvidenceDisposition(
            request_index=0,
            source="t@1",
            strength="informational",
            status=good_status,
        )
        assert d.status == good_status

    def test_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            EvidenceDisposition(
                request_index=0,
                source="t@1",
                strength="informational",
                status="not_a_valid_status",
            )
