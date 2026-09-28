"""skills-telemetry is an optional consumer, never a dependency.

Council emits OTLP spend spans (ADR-056) that skills-telemetry can read. That
must stay one-directional: council builds, tests, releases and runs the same
whether or not skills-telemetry, or its `stdtel` package, exists.

#707 briefly broke this by putting a `uvx stdtel-conform` job in `ci.yml`, so
every PR's CI depended on another project's package being published and
reachable. These tests pin the boundary rather than trusting a convention.
"""

import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _mentions_stdtel(text: str) -> bool:
    return bool(re.search(r"stdtel", text))


def test_no_runtime_or_test_dependency_on_stdtel():
    pyproject = (ROOT / "pyproject.toml").read_text()
    deps = [
        line
        for line in pyproject.splitlines()
        if not line.lstrip().startswith("#") and _mentions_stdtel(line)
    ]
    assert not deps, f"pyproject declares a stdtel dependency: {deps}"


def test_the_source_never_imports_stdtel():
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text()
        assert not re.search(r"^\s*(import|from)\s+stdtel\b", text, re.M), path


def test_the_required_ci_workflow_does_not_touch_stdtel():
    assert not _mentions_stdtel((WORKFLOWS / "ci.yml").read_text())


def test_every_workflow_that_uses_stdtel_is_advisory():
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text()
        if not _mentions_stdtel(text):
            continue
        workflow = yaml.safe_load(text)
        for name, job in workflow["jobs"].items():
            assert job.get("continue-on-error") is True, (
                f"{path.name}:{name} uses stdtel but can fail a build. "
                f"skills-telemetry is optional; mark the job continue-on-error."
            )


def test_the_emitter_is_off_without_an_endpoint(monkeypatch):
    from llm_council.observability import external_spend as ext

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    ext._reset_for_tests()
    assert ext.emit_external_spend(operation="consult", usage_summary={}) is False
