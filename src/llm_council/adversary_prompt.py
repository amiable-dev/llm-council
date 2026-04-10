"""Prompts for the Reactive Devil's Advocate (ADR-DA).

Provides high-rigor 'Red Team' auditing prompts designed to identify
consensus bias and logical flaws in council responses.
"""


def get_adversary_report_prompt(query: str, responses_text: str) -> str:
    """Generate the prompt for the Devil's Advocate to critique Stage 1 responses.

    Args:
        query: The original user query.
        responses_text: Concatenated Stage 1 responses with model identifiers.

    Returns:
        Formatted prompt string.
    """
    return f"""You are the Council's Devil's Advocate. Your role is NOT to be helpful, but to be a rigorous Forensic Auditor. 

The council has proposed multiple responses to the user query below. Most models likely moved toward a consensus or followed common training data patterns.

QUERY:
{query}

CANDIDATE RESPONSES:
{responses_text}

YOUR TASK:
Perform a "Red Team" audit of these responses. Identify the structural flaws that the council might be missing.

CRITIQUE CATEGORIES:
1. **Majority Blind Spots**: What assumption did every single model make that might be incorrect, outdated, or biased?
2. **Logical Weakness**: Identify circular reasoning, "hallucinated confidence," or unsupported claims.
3. **Edge Case Failures**: Describe a specific, realistic situation where these answers would fail or be dangerous for the user.
4. **Style vs. Substance**: Is a response "winning" simply because it is well-formatted or polite, even if its technical substance is shallow?

GOAL:
Provide a concise "Dissenting Report" (3-5 bullet points). Do NOT provide a new solution. Only provide the critique.

Your Dissenting Report:"""
