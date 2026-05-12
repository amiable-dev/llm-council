"""ADR-042 byte-identity regression: chairman prompts must render identically
to pre-ADR-042 baselines when dispositions_instruction is None.

The dispositions_instruction kwarg is new in ADR-042. The invariant is that
calling existing helpers without it produces output unchanged from before.
"""

from llm_council.verdict import (
    VerdictType,
    _get_binary_chairman_prompt,
    _get_synthesis_chairman_prompt,
    _get_tie_breaker_chairman_prompt,
    get_chairman_prompt,
)


# Captured pre-ADR-042 prompts (verbatim from the previous git revision).
EXPECTED_BINARY = """You are the Chairman synthesizing the council's deliberation.

The council has reviewed and ranked responses to the following query:

QUERY: TEST_QUERY

Based on the rankings and evaluations below, you must render a BINARY VERDICT.

Your task: Determine whether the proposed action/answer should be APPROVED or REJECTED.

Consider:
- Overall quality and accuracy of the top-ranked responses
- Consensus among council members
- Any safety or quality concerns raised in evaluations

RANKINGS SUMMARY:
TEST_RANKINGS

Output ONLY valid JSON with no additional text:
{
  "verdict": "approved" or "rejected",
  "confidence": 0.0 to 1.0,
  "rationale": "Brief explanation of the decision basis"
}"""

EXPECTED_TIE_BREAKER = """You are the Chairman resolving a DEADLOCKED deliberation.

The council is evenly split on the following query:

QUERY: TEST_QUERY

You must cast the DECIDING VOTE to break the tie.

TOP CANDIDATES (within scoring threshold):
TEST_CANDIDATES

FULL RANKINGS:
TEST_RANKINGS

As Chairman, carefully consider:
1. Subtle quality differences between top candidates
2. Any edge cases or concerns raised in evaluations
3. Which response best serves the user's intent

Output ONLY valid JSON with no additional text:
{
  "verdict": "approved" or "rejected",
  "confidence": 0.0 to 1.0,
  "rationale": "Explain which candidate you chose and why",
  "deadlock_resolution": "Brief explanation of how you broke the tie"
}"""

EXPECTED_SYNTHESIS = """You are the Chairman synthesizing the council's deliberation.

The council has reviewed and ranked responses to:

QUERY: TEST_QUERY

RANKINGS SUMMARY:
TEST_RANKINGS

Synthesize the best elements from the top-ranked responses into a comprehensive,
well-structured final answer. Incorporate the strongest arguments and address
any concerns raised during peer review.

Provide your synthesized response:"""


class TestChairmanPromptByteIdentity:
    """Pre-ADR-042 byte-identity must hold when dispositions_instruction=None."""

    def test_binary_default_kwarg(self):
        prompt = _get_binary_chairman_prompt("TEST_QUERY", "TEST_RANKINGS")
        assert prompt == EXPECTED_BINARY

    def test_binary_explicit_none(self):
        prompt = _get_binary_chairman_prompt(
            "TEST_QUERY", "TEST_RANKINGS", dispositions_instruction=None
        )
        assert prompt == EXPECTED_BINARY

    def test_tie_breaker_default(self):
        prompt = _get_tie_breaker_chairman_prompt("TEST_QUERY", "TEST_RANKINGS", "TEST_CANDIDATES")
        assert prompt == EXPECTED_TIE_BREAKER

    def test_synthesis_default(self):
        prompt = _get_synthesis_chairman_prompt("TEST_QUERY", "TEST_RANKINGS")
        assert prompt == EXPECTED_SYNTHESIS

    def test_get_chairman_prompt_binary_routes_correctly(self):
        prompt = get_chairman_prompt(VerdictType.BINARY, "TEST_QUERY", "TEST_RANKINGS")
        assert prompt == EXPECTED_BINARY

    def test_get_chairman_prompt_tie_breaker_routes_correctly(self):
        prompt = get_chairman_prompt(
            VerdictType.TIE_BREAKER,
            "TEST_QUERY",
            "TEST_RANKINGS",
            top_candidates="TEST_CANDIDATES",
        )
        assert prompt == EXPECTED_TIE_BREAKER


class TestDispositionsBlockInjection:
    """When dispositions_instruction is provided, it must appear in the prompt."""

    def test_binary_inserts_dispositions_block(self):
        block = "[DISPOSITIONS_BLOCK_MARKER]"
        prompt = _get_binary_chairman_prompt(
            "TEST_QUERY", "TEST_RANKINGS", dispositions_instruction=block
        )
        assert block in prompt
        # And RANKINGS still precedes it.
        assert prompt.index("RANKINGS SUMMARY:") < prompt.index(block)
        assert prompt.index(block) < prompt.index("Output ONLY valid JSON")

    def test_tie_breaker_inserts_dispositions_block(self):
        block = "[DISPOSITIONS_BLOCK_MARKER]"
        prompt = _get_tie_breaker_chairman_prompt(
            "TEST_QUERY",
            "TEST_RANKINGS",
            "TEST_CANDIDATES",
            dispositions_instruction=block,
        )
        assert block in prompt
        assert prompt.index("FULL RANKINGS:") < prompt.index(block)
        assert prompt.index(block) < prompt.index("As Chairman, carefully consider")

    def test_synthesis_inserts_dispositions_block(self):
        block = "[DISPOSITIONS_BLOCK_MARKER]"
        prompt = _get_synthesis_chairman_prompt(
            "TEST_QUERY", "TEST_RANKINGS", dispositions_instruction=block
        )
        assert block in prompt
