"""#664: evidence dispositions are lost whenever structured findings is on.

ADR-042 asks the chairman for a fenced ```json block containing
`evidence_dispositions`. ADR-051 structured findings asks it for ONE top-level
JSON object. Under both, the chairman does the sensible thing and nests the
dispositions fence inside the findings object's `rationale` **string** — where
its newlines are the two-character escape `\\n`, so the fence regex's mandatory
real newline never matches. `parse_evidence_dispositions` finds no block and
marks every submitted item `parser_error`, discarding per-item reasoning that
is sitting right there in the response.

Observed live on `verification_id` 66ab5ebf: 3 informational items, all three
`parser_error`, `council_confirmed: null`, while the response contained a
well-formed dispositions array with correct rationale for each.

Soft-fail behaving as designed; the *detection* is what's wrong. ADR-052 is
driving structured findings toward default-ON, which would make this the
normal case rather than an opt-in one.
"""

import json
from typing import List, Tuple

from llm_council.verdict import parse_evidence_dispositions
from llm_council.verification.api import EvidenceItem


def _items(*specs) -> List[Tuple[int, EvidenceItem]]:
    return [
        (i, EvidenceItem(source=src, content="x", strength=stren, evidence_id=eid))
        for i, (src, stren, eid) in enumerate(specs)
    ]


DISPOSITIONS = {
    "evidence_dispositions": [
        {
            "evidence_id": "id-a",
            "source": "a@1",
            "strength": "informational",
            "status": "acknowledged",
            "council_confirmed": None,
            "council_rationale": "grounds the dead-config claim",
        },
        {
            "evidence_id": "id-b",
            "source": "b@1",
            "strength": "blocking",
            "status": "confirmed",
            "council_confirmed": True,
            "council_rationale": "the quoted test asserts only the constant",
        },
    ]
}


def _structured_findings_response() -> str:
    """The exact shape observed in the field, built the way the model builds it.

    One top-level findings object whose `rationale` value is a string that
    happens to contain a fenced dispositions block. json.dumps performs the
    escaping, so this reproduces the real bytes rather than approximating them.
    """
    inner_fence = "```json\n" + json.dumps(DISPOSITIONS, indent=2) + "\n```"
    return json.dumps(
        {
            "findings": [
                {"severity": "info", "description": "code facts check out", "location": None}
            ],
            "verdict": "rejected",
            "confidence": 0.86,
            "rationale": "The council is unanimous.\n\n" + inner_fence,
        },
        indent=2,
    )


class TestNestedDispositionsAreFound:
    def test_the_reproduction_actually_reproduces(self):
        """Guard the guard: if this stops being escaped, the test is vacuous."""
        raw = _structured_findings_response()
        assert "evidence_dispositions" in raw
        assert "```" in raw
        # The fence is inside a JSON string, so its newlines are escaped.
        assert "```json\\n" in raw

    def test_dispositions_survive_nesting_in_a_findings_rationale(self):
        items = _items(("a@1", "informational", "id-a"), ("b@1", "blocking", "id-b"))
        dispositions, _ = parse_evidence_dispositions(_structured_findings_response(), items)

        by_id = {d.evidence_id: d for d in dispositions}
        assert by_id["id-a"].status == "acknowledged"
        assert by_id["id-a"].council_rationale == "grounds the dead-config claim"
        assert by_id["id-b"].status == "confirmed"
        assert by_id["id-b"].council_confirmed is True

    def test_top_level_key_is_also_honoured(self):
        """Future-proofs the cleaner fix: dispositions as a key of the findings
        object rather than a fenced sibling. Should already work if we stop
        insisting on a fence."""
        items = _items(("a@1", "informational", "id-a"))
        response = json.dumps(
            {
                "findings": [],
                "verdict": "approved",
                "confidence": 0.9,
                "rationale": "fine",
                **DISPOSITIONS,
            }
        )
        dispositions, _ = parse_evidence_dispositions(response, items)
        assert dispositions[0].status == "acknowledged"

    def test_plain_fenced_block_still_works(self):
        """The pre-existing ADR-042 path must be untouched."""
        items = _items(("a@1", "informational", "id-a"))
        response = (
            '{"verdict": "approved", "confidence": 0.9, "rationale": "fine"}\n\n'
            "```json\n" + json.dumps(DISPOSITIONS) + "\n```"
        )
        dispositions, _ = parse_evidence_dispositions(response, items)
        assert dispositions[0].status == "acknowledged"

    def test_genuinely_absent_dispositions_still_parser_error(self):
        """No false positives: a response with no dispositions anywhere must
        keep reporting parser_error rather than inventing something."""
        items = _items(("a@1", "informational", "id-a"))
        response = json.dumps(
            {"findings": [], "verdict": "approved", "confidence": 0.9, "rationale": "no evidence"}
        )
        dispositions, _ = parse_evidence_dispositions(response, items)
        assert dispositions[0].status == "parser_error"
        assert dispositions[0].council_confirmed is None

    def test_malformed_nested_block_does_not_raise(self):
        """Soft-fail is the contract — a truncated nested block degrades to
        parser_error, never an exception."""
        items = _items(("a@1", "informational", "id-a"))
        response = json.dumps(
            {
                "findings": [],
                "verdict": "approved",
                "confidence": 0.9,
                "rationale": '```json\n{"evidence_dispositions": [{"evidence_id": "id-a",\n```',
            }
        )
        dispositions, _ = parse_evidence_dispositions(response, items)
        assert dispositions[0].status == "parser_error"

    def test_hallucinated_ids_still_dropped_when_nested(self):
        """The hallucination guard must apply on the nested path too."""
        items = _items(("a@1", "informational", "id-a"))
        payload = {
            "evidence_dispositions": [
                {
                    "evidence_id": "id-not-submitted",
                    "source": "z@9",
                    "strength": "blocking",
                    "status": "confirmed",
                    "council_confirmed": True,
                    "council_rationale": "invented",
                }
            ]
        }
        response = json.dumps(
            {
                "findings": [],
                "verdict": "approved",
                "confidence": 0.9,
                "rationale": "x\n\n```json\n" + json.dumps(payload) + "\n```",
            }
        )
        dispositions, _ = parse_evidence_dispositions(response, items)
        assert len(dispositions) == 1
        assert dispositions[0].evidence_id == "id-a"
        assert dispositions[0].status == "parser_error"
