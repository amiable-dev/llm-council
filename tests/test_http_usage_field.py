"""CouncilResponse exposes a typed, OpenAPI-documented usage field (ADR-011 #360)."""

from llm_council.http_server import CouncilResponse, UsageSummary


def test_usage_summary_coerces_from_metadata_dict():
    usage = {
        "by_stage": {"stage1": {"total_tokens": 40, "cost_usd": 0.01}},
        "by_model": {"openai/gpt-4o": {"total_tokens": 40, "cost_usd": 0.01}},
        "total": {"total_tokens": 40, "cost_usd": 0.01, "cached_tokens": 5},
    }
    resp = CouncilResponse(stage1=[], stage2=[], stage3={}, metadata={"usage": usage}, usage=usage)
    assert isinstance(resp.usage, UsageSummary)
    assert resp.usage.total["cost_usd"] == 0.01
    assert resp.usage.by_model["openai/gpt-4o"]["total_tokens"] == 40


def test_usage_optional_when_absent():
    resp = CouncilResponse(stage1=[], stage2=[], stage3={}, metadata={})
    assert resp.usage is None


def test_usage_present_in_openapi_schema():
    schema = CouncilResponse.model_json_schema()
    assert "usage" in schema["properties"]
