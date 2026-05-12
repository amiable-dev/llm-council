"""Tests for ADR-042 parse_evidence_dispositions.

TDD Red Phase: These tests should fail until parse_evidence_dispositions is
implemented in src/llm_council/verdict.py.

Covers spec §14.5 (Disposition Parser).
"""

from typing import List, Tuple

from llm_council.verdict import parse_evidence_dispositions
from llm_council.verification.api import EvidenceItem


def _items(*specs) -> List[Tuple[int, EvidenceItem]]:
    """Helper: build (request_index, EvidenceItem) tuples.

    specs is a list of (source, strength, evidence_id) — evidence_id may be None.
    """
    return [
        (i, EvidenceItem(source=src, content="x", strength=stren, evidence_id=eid))
        for i, (src, stren, eid) in enumerate(specs)
    ]


class TestDispositionParser:
    """Parser robustness: hallucinations dropped, missing items → parser_error."""

    def test_well_formed_dispositions(self):
        items = _items(
            ("a@1", "informational", "id-a"),
            ("b@1", "blocking", "id-b"),
        )
        chairman = """
        {"verdict": "approved", "confidence": 0.9, "rationale": "fine"}

        ```json
        {
          "evidence_dispositions": [
            {"evidence_id": "id-a", "source": "a@1", "strength": "informational",
             "status": "acknowledged", "council_confirmed": null, "council_rationale": "noted"},
            {"evidence_id": "id-b", "source": "b@1", "strength": "blocking",
             "status": "confirmed", "council_confirmed": true, "council_rationale": "verified"}
          ]
        }
        ```
        """
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        assert len(dispositions) == 2
        assert dispositions[0].evidence_id == "id-a"
        assert dispositions[0].status == "acknowledged"
        assert dispositions[0].council_confirmed is None
        assert dispositions[1].evidence_id == "id-b"
        assert dispositions[1].status == "confirmed"
        assert dispositions[1].council_confirmed is True

    def test_no_json_block_returns_parser_error_for_all(self):
        items = _items(("a@1", "informational", None))
        dispositions, _ = parse_evidence_dispositions("no json here", items)
        assert len(dispositions) == 1
        assert dispositions[0].status == "parser_error"
        assert dispositions[0].evidence_id == "auto-0"

    def test_malformed_json_returns_parser_error_for_all(self):
        items = _items(("a@1", "informational", None))
        chairman = "```json\n{not valid json\n```"
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        assert dispositions[0].status == "parser_error"

    def test_json_block_missing_dispositions_key_returns_parser_error(self):
        items = _items(("a@1", "informational", "id-a"))
        chairman = '```json\n{"verdict": "approved"}\n```'
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        assert dispositions[0].status == "parser_error"

    def test_hallucinated_source_silently_dropped(self):
        items = _items(("a@1", "informational", "id-a"))
        chairman = """```json
        {"evidence_dispositions": [
          {"evidence_id": "hallucinated", "source": "h@1", "strength": "informational",
           "status": "acknowledged"}
        ]}
        ```"""
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        # Hallucinated entry dropped; submitted item gets parser_error
        # (not in chairman output).
        assert len(dispositions) == 1
        assert dispositions[0].evidence_id == "id-a"
        assert dispositions[0].status == "parser_error"

    def test_missing_item_gets_parser_error(self):
        items = _items(
            ("a@1", "blocking", "id-a"),
            ("b@1", "blocking", "id-b"),
        )
        chairman = """```json
        {"evidence_dispositions": [
          {"evidence_id": "id-a", "source": "a@1", "strength": "blocking",
           "status": "confirmed", "council_confirmed": true}
        ]}
        ```"""
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        assert len(dispositions) == 2
        by_id = {d.evidence_id: d for d in dispositions}
        assert by_id["id-a"].status == "confirmed"
        assert by_id["id-b"].status == "parser_error"

    def test_invalid_status_falls_back_to_parser_error(self):
        items = _items(("a@1", "blocking", "id-a"))
        chairman = """```json
        {"evidence_dispositions": [
          {"evidence_id": "id-a", "source": "a@1", "strength": "blocking",
           "status": "maybe", "council_confirmed": true}
        ]}
        ```"""
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        assert dispositions[0].status == "parser_error"

    def test_council_confirmed_forced_none_for_acknowledged(self):
        # Even if the Chairman tries to set council_confirmed=True for an
        # informational/acknowledged item, the parser forces it to None.
        items = _items(("a@1", "informational", "id-a"))
        chairman = """```json
        {"evidence_dispositions": [
          {"evidence_id": "id-a", "source": "a@1", "strength": "informational",
           "status": "acknowledged", "council_confirmed": true, "council_rationale": "x"}
        ]}
        ```"""
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        assert dispositions[0].council_confirmed is None

    def test_council_confirmed_forced_false_for_rejected(self):
        # Even if Chairman omits council_confirmed for a rejected blocking
        # item, the parser forces it to False from the status.
        items = _items(("a@1", "blocking", "id-a"))
        chairman = """```json
        {"evidence_dispositions": [
          {"evidence_id": "id-a", "source": "a@1", "strength": "blocking",
           "status": "rejected", "council_confirmed": null, "council_rationale": "no"}
        ]}
        ```"""
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        assert dispositions[0].status == "rejected"
        assert dispositions[0].council_confirmed is False

    def test_auto_id_fallback(self):
        # Item with no evidence_id uses auto-<request_index>.
        items = _items(("a@1", "informational", None))
        chairman = """```json
        {"evidence_dispositions": [
          {"evidence_id": "auto-0", "source": "a@1", "strength": "informational",
           "status": "acknowledged"}
        ]}
        ```"""
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        assert dispositions[0].evidence_id == "auto-0"
        assert dispositions[0].status == "acknowledged"

    def test_dispositions_in_second_json_block(self):
        # Chairman emits verdict JSON first, dispositions JSON second.
        # Parser must scan ALL fenced blocks and pick the one with the key.
        items = _items(("a@1", "informational", "id-a"))
        chairman = """
        Some prose...

        ```json
        {"verdict": "approved", "confidence": 0.9, "rationale": "fine"}
        ```

        More prose...

        ```json
        {"evidence_dispositions": [
          {"evidence_id": "id-a", "source": "a@1", "strength": "informational",
           "status": "acknowledged"}
        ]}
        ```
        """
        dispositions, _ = parse_evidence_dispositions(chairman, items)
        assert dispositions[0].status == "acknowledged"
