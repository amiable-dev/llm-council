"""skills-telemetry is an optional consumer, never a dependency.

Council emits OTLP spend spans (ADR-056) that skills-telemetry can read. That
must stay one-directional: council builds, tests, releases and runs the same
whether or not skills-telemetry, or its `stdtel` package, exists.

#707 briefly broke this by putting a `uvx stdtel-conform` job in `ci.yml`, so
every PR's CI depended on another project's package being published and
reachable. These tests pin the boundary rather than trusting a convention.
"""

import ast
import pathlib
import re

import pytest

tomllib = pytest.importorskip("tomllib")  # stdlib from 3.11; council supports 3.10
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
STDTEL = re.compile(r"stdtel", re.IGNORECASE)


def _workflow_files():
    # GitHub Actions accepts both extensions.
    return sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])


def test_no_declared_dependency_on_stdtel():
    """Parsed, not grepped: a comment mentioning stdtel is fine; a
    requirement in any dependency group or extra is not."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    requirements = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        requirements.extend(group)
    offenders = [r for r in requirements if STDTEL.match(r.strip())]
    assert not offenders, f"pyproject declares a stdtel dependency: {offenders}"


@pytest.mark.parametrize("tree", ["src", "tests"])
def test_nothing_imports_stdtel(tree):
    offenders = []
    for path in (ROOT / tree).rglob("*.py"):
        module = ast.parse(path.read_text())
        for node in ast.walk(module):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif (
                isinstance(node, ast.Call)
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and getattr(node.func, "attr", getattr(node.func, "id", "")) == "import_module"
            ):
                names = [node.args[0].value]
            if any(n.split(".")[0].lower() == "stdtel" for n in names):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, offenders


def test_the_required_ci_workflow_does_not_touch_stdtel():
    assert not STDTEL.search((WORKFLOWS / "ci.yml").read_text())


def test_every_workflow_that_uses_stdtel_is_advisory():
    checked = 0
    for path in _workflow_files():
        text = path.read_text()
        if not STDTEL.search(text):
            continue
        jobs = (yaml.safe_load(text) or {}).get("jobs") or {}
        for name, job in jobs.items():
            assert "uses" not in job, (
                f"{path.name}:{name} calls a reusable workflow, which cannot be "
                f"marked continue-on-error; keep stdtel steps inline."
            )
            assert job.get("continue-on-error") is True, (
                f"{path.name}:{name} uses stdtel but can fail a build. "
                f"skills-telemetry is optional; mark the job continue-on-error."
            )
            checked += 1
    assert checked, "expected the advisory external-contract workflow to be checked"


def test_piped_stdtel_steps_fail_on_an_upstream_error():
    """Without pipefail, an unreachable `stdtel-conform --print-contract`
    would hand the checker empty input and report the checker's exit code:
    a false green, even for an advisory job."""
    for path in _workflow_files():
        text = path.read_text()
        if not STDTEL.search(text):
            continue
        for job in ((yaml.safe_load(text) or {}).get("jobs") or {}).values():
            defaults = (job.get("defaults") or {}).get("run") or {}
            for step in job.get("steps", []):
                run = step.get("run", "")
                if "|" in run and STDTEL.search(run):
                    shell = step.get("shell") or defaults.get("shell")
                    assert shell == "bash" or "pipefail" in run, (path.name, step.get("name"))


class TestTheEmitterIsInertWithoutAnEndpoint:
    """With a positive control, so the negative case cannot pass vacuously
    (required CI does not install the [otel] extra)."""

    @pytest.fixture
    def fake_tracer(self, monkeypatch):
        from contextlib import contextmanager

        from llm_council.observability import external_spend as ext

        spans = []

        class Tracer:
            @contextmanager
            def start_as_current_span(self, name):
                class Span:
                    def set_attributes(self, attrs):
                        spans.append(attrs)

                yield Span()

        ext._reset_for_tests()
        monkeypatch.setattr(ext, "_get_tracer", lambda: Tracer())
        yield ext, spans
        ext._reset_for_tests()

    def test_with_an_endpoint_a_span_is_emitted(self, fake_tracer, monkeypatch):
        ext, spans = fake_tracer
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
        assert ext.emit_external_spend(operation="consult", usage_summary={}) is True
        assert len(spans) == 1

    def test_without_an_endpoint_nothing_is_emitted(self, fake_tracer, monkeypatch):
        ext, spans = fake_tracer
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        assert ext.emit_external_spend(operation="consult", usage_summary={}) is False
        assert spans == []
