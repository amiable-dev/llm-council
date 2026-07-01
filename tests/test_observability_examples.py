"""Validate the bundled observability templates parse (ADR-011 Phase 2, #361)."""

import json
from pathlib import Path

import pytest

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "observability"


def test_grafana_dashboard_is_valid_json():
    data = json.loads((_EXAMPLES / "grafana-dashboard.json").read_text())
    assert data["title"].startswith("LLM Council")
    assert len(data["panels"]) >= 1
    # References the OTel GenAI metric names we emit.
    exprs = " ".join(t["expr"] for p in data["panels"] for t in p.get("targets", []))
    assert "gen_ai_client_token_usage" in exprs
    assert "llm_council_cost_usd" in exprs


@pytest.mark.parametrize(
    "name",
    [
        "docker-compose.observability.yml",
        "otel-collector-config.yaml",
        "prometheus.yml",
    ],
)
def test_yaml_templates_parse(name):
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load((_EXAMPLES / name).read_text())
    assert isinstance(doc, dict) and doc


def test_readme_present():
    assert (_EXAMPLES / "README.md").exists()
