"""Documentation drift guards (#448, epic #443).

The repo drift-tests its server card and bench baselines; docs get the same
treatment: these tests fail when code and documentation diverge.
"""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "llm_council"
ENV_REFERENCE = REPO / "docs" / "reference" / "environment-variables.md"

# Literal reads: os.getenv("NAME") — closing quote required.
ENV_READ_LITERAL = re.compile(
    r'os\.(?:getenv|environ\.get|environ\[)\(?\s*["\']([A-Z][A-Z0-9_]+)["\']'
)
# Dynamic f-string reads: os.getenv(f"PREFIX_{expr}") — capture the prefix.
ENV_READ_DYNAMIC = re.compile(
    r'os\.(?:getenv|environ\.get|environ\[)\(?\s*[fF]["\']([A-Z][A-Z0-9_]+)\{'
)
# The one sanctioned dynamic pattern: LLM_COUNCIL_MODELS_{tier.upper()} —
# the capture truncates at the f-string expression, so expand by PREFIX.
DYNAMIC_EXPANSIONS = {
    "LLM_COUNCIL_MODELS_": [
        f"LLM_COUNCIL_MODELS_{t}" for t in ("QUICK", "BALANCED", "HIGH", "REASONING")
    ],
}
# Client-side vars we document but do not read ourselves.
DOC_ONLY_ALLOWED = {"MCP_TIMEOUT", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "HOME"}


def _env_reads_in_src() -> set:
    names: set = set()
    for f in SRC.rglob("*.py"):
        text = f.read_text()
        names.update(ENV_READ_LITERAL.findall(text))
        for prefix in ENV_READ_DYNAMIC.findall(text):
            expansion = DYNAMIC_EXPANSIONS.get(prefix)
            assert expansion, (
                f"unsanctioned dynamic env read prefix {prefix!r} in {f} — "
                "add its expansion to DYNAMIC_EXPANSIONS"
            )
            names.update(expansion)
    return names


def _documented_in_reference() -> set:
    text = ENV_REFERENCE.read_text()
    return set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \|", text, re.M))


class TestEnvReferenceDrift:
    def test_every_env_read_is_documented(self):
        undocumented = sorted(_env_reads_in_src() - _documented_in_reference())
        assert not undocumented, (
            "env vars read in src but missing from "
            f"docs/reference/environment-variables.md: {undocumented}"
        )

    def test_no_phantom_vars_documented(self):
        phantom = sorted(
            _documented_in_reference() - _env_reads_in_src() - DOC_ONLY_ALLOWED
        )
        assert not phantom, (
            "documented env vars that no code reads (the #446 failure class): "
            f"{phantom}"
        )

    def test_readme_mentions_only_real_vars(self):
        readme = (REPO / "README.md").read_text()
        mentioned = set(re.findall(r"`(LLM_COUNCIL_[A-Z0-9_]+)`", readme))
        real = _env_reads_in_src()
        phantom = sorted(mentioned - real)
        assert not phantom, f"README documents nonexistent env vars: {phantom}"


class TestAdrNavDrift:
    def test_every_adr_reachable_from_mkdocs_nav(self):
        nav = (REPO / "mkdocs.yml").read_text()
        skip = {"ADR-000-template.md"}
        missing = [
            f.name
            for f in sorted((REPO / "docs" / "adr").glob("ADR-*.md"))
            if f.name not in skip and f"adr/{f.name}" not in nav
        ]
        assert not missing, f"ADRs unreachable from the site nav: {missing}"


class TestGuideSnippets:
    GUIDES = [
        REPO / "docs" / "getting-started" / "quickstart.md",
        REPO / "docs" / "guides" / "python.md",
    ]

    def test_python_snippets_parse_and_import(self):
        failures = []
        for guide in self.GUIDES:
            text = guide.read_text()
            for i, block in enumerate(re.findall(r"```python\n(.*?)```", text, re.S)):
                try:
                    ast.parse(block)
                except SyntaxError as e:
                    failures.append(f"{guide.name}#{i}: syntax: {e}")
                    continue
                for line in block.splitlines():
                    line = line.strip()
                    if line.startswith(("from llm_council", "import llm_council")):
                        try:
                            exec(line, {})  # imports only, never bodies
                        except Exception as e:
                            failures.append(f"{guide.name}#{i}: {line} -> {e}")
        assert not failures, "\n".join(failures)
