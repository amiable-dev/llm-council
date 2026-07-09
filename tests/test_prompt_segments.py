"""ADR-049 D1 (#459): stable-prefix-first prompt assembly.

The verification prompt previously OPENED with the snapshot SHA — a
cache-buster in the first bytes of every round — with the stable
instructions at the end. Segments now render in stability order:
static head -> evidence -> subject -> volatile tail (SHA lives here).
"""

from unittest.mock import AsyncMock, patch

import pytest

from llm_council.verification.api import _build_verification_prompt


def _patch_files(content_by_call):
    """Patch file fetching to return supplied content per call."""
    side = [
        (content, {"expanded_paths": ["src/x.py"], "paths_truncated": False,
                   "expansion_warnings": []})
        for content in content_by_call
    ]
    return patch(
        "llm_council.verification.api._fetch_files_for_verification_async_with_metadata",
        new_callable=AsyncMock,
        side_effect=side,
    )


async def _build(sha, files_content, rubric_focus="Security", evidence=None):
    with _patch_files([files_content]):
        return await _build_verification_prompt(
            snapshot_id=sha,
            target_paths=["src/x.py"],
            rubric_focus=rubric_focus,
            evidence=evidence,
            tier="balanced",
        )


class TestSegmentOrdering:
    @pytest.mark.asyncio
    async def test_sha_only_in_volatile_tail(self):
        prompt, info = await _build("abc1234def", "def f():\n    return 1\n")
        segments = info["segments"]
        names = [s["name"] for s in segments]
        assert names == ["static_head", "evidence", "subject", "volatile_tail"]
        tail = next(s for s in segments if s["name"] == "volatile_tail")
        # The SHA appears in the tail and NOWHERE before it.
        assert "abc1234def" in prompt[tail["start"]:tail["end"]]
        assert "abc1234def" not in prompt[: tail["start"]]

    @pytest.mark.asyncio
    async def test_segment_offsets_reconstruct_prompt(self):
        prompt, info = await _build("abc1234def", "content\n")
        segments = info["segments"]
        assert segments[0]["start"] == 0
        assert segments[-1]["end"] == len(prompt)
        for a, b in zip(segments, segments[1:]):
            assert a["end"] == b["start"]  # contiguous, no gaps
        for s in segments:
            assert s["est_tokens"] == (s["end"] - s["start"]) // 4

    @pytest.mark.asyncio
    async def test_evidence_after_head_before_subject(self):
        evidence = [{
            "id": "e1", "source": "linter", "strength": "informational",
            "content": "unused import on line 3",
        }]
        from llm_council.verification.schemas import EvidenceItem

        prompt, info = await _build(
            "abc1234def", "code\n",
            evidence=[EvidenceItem(**e) for e in evidence],
        )
        head = next(s for s in info["segments"] if s["name"] == "static_head")
        subj = next(s for s in info["segments"] if s["name"] == "subject")
        pos = prompt.index("unused import on line 3")
        assert head["end"] <= pos < subj["start"]


class TestByteStabilityAcrossRounds:
    @pytest.mark.asyncio
    async def test_stable_through_evidence_when_only_sha_and_code_change(self):
        # ADR-049 golden-file criterion: rounds r1/r2 of the same subject —
        # different SHA, one changed code line — are byte-identical through
        # the end of the evidence segment.
        p1, i1 = await _build("aaaa111", "line1\nline2\nline3\n")
        p2, i2 = await _build("bbbb222", "line1\nCHANGED\nline3\n")
        e1 = next(s for s in i1["segments"] if s["name"] == "evidence")
        e2 = next(s for s in i2["segments"] if s["name"] == "evidence")
        assert e1["end"] == e2["end"]
        assert p1[: e1["end"]] == p2[: e2["end"]]  # byte-identical prefix

    @pytest.mark.asyncio
    async def test_identical_subject_stable_through_subject_segment(self):
        p1, i1 = await _build("aaaa111", "same\n")
        p2, i2 = await _build("bbbb222", "same\n")
        s1 = next(s for s in i1["segments"] if s["name"] == "subject")
        assert p1[: s1["end"]] == p2[: s1["end"]]

    @pytest.mark.asyncio
    async def test_no_timestamps_or_uuids_above_tail(self):
        import re

        prompt, info = await _build("abc1234def", "x\n")
        tail = next(s for s in info["segments"] if s["name"] == "volatile_tail")
        head_to_subject = prompt[: tail["start"]]
        assert not re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:", head_to_subject)
        assert not re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            head_to_subject,
        )


class TestExistingPinsPreserved:
    @pytest.mark.asyncio
    async def test_focus_before_evidence_before_code(self):
        # ADR-042 §6 ordering contract survives the re-order.
        from llm_council.verification.schemas import EvidenceItem

        prompt, _ = await _build(
            "abc1234def", "body\n",
            evidence=[EvidenceItem(id="e1", source="s", strength="informational",
                                   content="finding-xyz")],
        )
        # Anchor on the distinctive focus phrase — a bare "Security" could
        # false-positive on the instructions' "security vulnerabilities".
        assert prompt.index("**Focus Area**: Security") < prompt.index("finding-xyz")
        assert prompt.index("finding-xyz") < prompt.index("## Code to Review")
