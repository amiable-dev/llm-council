"""Markdown formatting and status reporting utilities."""

from typing import Dict, Any, Optional
from llm_council.gateway_adapter import STATUS_OK


def generate_partial_warning(
    model_statuses: Dict[str, Dict[str, Any]], requested: int
) -> Optional[str]:
    """Generate a warning message for partial results (ADR-012)."""
    ok_count = sum(1 for s in model_statuses.values() if s.get("status") == STATUS_OK)

    if ok_count == requested:
        return None

    failed_models = [
        model for model, status in model_statuses.items() if status.get("status") != STATUS_OK
    ]

    failed_reasons = []
    for model in failed_models:
        status = model_statuses[model].get("status", "unknown")
        model_short = model.split("/")[-1]
        failed_reasons.append(f"{model_short} ({status})")

    return (
        f"This answer is based on {ok_count} of {requested} intended models. "
        f"Did not respond: {', '.join(failed_reasons)}."
    )


async def generate_conversation_title(user_query: str, council_id: Optional[str] = None) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message
        council_id: Optional ID for tracking

    Returns:
        A short title (3-5 words)
    """
    from llm_council.gateway_adapter import query_model

    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model(
        "google/gemini-2.5-flash", messages, timeout=30.0, council_id=council_id
    )

    if response is None:
        return "New Conversation"

    title = response.get("content", "New Conversation").strip()
    title = title.strip("\"'")
    if len(title) > 50:
        title = title[:47] + "..."

    return title
