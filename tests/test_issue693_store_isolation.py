"""#693 — the test suite must not write into the operator's real store.

## What happened

`~/.llm-council/performance_metrics.jsonl` on the maintainer's machine held
**1,868 records for `model_id: "test/model-a"` out of 7,597** — about a quarter
of the file, byte-identical apart from the session id, matching the fixture in
`tests/test_adr041_verification_telemetry.py`. The newest of them was written
during a gate run on 2026-09-18, so this was ongoing, not historical.

It mattered far beyond tidiness. Those rows carry `cost_usd: null`, so anyone
totalling cost from the file saw roughly a third of rows missing a cost and
concluded the capture pipeline was broken. It was not: every real record from
2026-07-04 onward carries a cost. The fixtures made a working pipeline look
faulty and sent the investigation at the wrong defect.

## Why an env-var fixture alone would not have fixed it

`performance/integration.py` resolved BOTH the store path and the enabled flag
at **import time** (`PERFORMANCE_STORE_PATH`, `PERFORMANCE_TRACKING_ENABLED`),
and `get_tracker()` memoises a singleton built from the former. So a test that
sets `LLM_COUNCIL_PERFORMANCE_STORE` after the module is imported — which is
every test, since collection imports first — changes nothing. That is the
"it depends what was imported first" class of bug, and the fix is to resolve
lazily so the question cannot be asked.

## What is asserted here

The guard is the load-bearing part: `test_no_test_can_write_under_the_real_home`
fails if the resolved store path is anywhere under the real `HOME`. An autouse
fixture redirecting to `tmp_path` is only as good as the next person's memory;
a guard that fails the build is not.
"""

import json
import os
from pathlib import Path

import pytest

REAL_HOME = Path(os.path.expanduser("~")).resolve()


class TestResolutionIsLazy:
    """Import-time resolution is what made the env-var escape hatch useless."""

    def test_store_path_follows_the_env_var_set_after_import(self, monkeypatch, tmp_path):
        from llm_council.performance import integration

        target = tmp_path / "somewhere-else.jsonl"
        monkeypatch.setenv("LLM_COUNCIL_PERFORMANCE_STORE", str(target))
        assert integration.resolve_store_path() == target

    def test_tracking_flag_follows_the_env_var_set_after_import(self, monkeypatch):
        """The enabled flag had the same import-time defect as the path. A test
        that disables tracking after import was silently ignored."""
        from llm_council.performance import integration

        monkeypatch.setenv("LLM_COUNCIL_PERFORMANCE_TRACKING", "false")
        assert integration.tracking_enabled() is False
        monkeypatch.setenv("LLM_COUNCIL_PERFORMANCE_TRACKING", "true")
        assert integration.tracking_enabled() is True

    def test_the_tracker_singleton_follows_the_path(self, monkeypatch, tmp_path):
        """`get_tracker()` memoises. A tracker built before a redirect would
        keep writing to the old path, so the reset has to be part of the
        contract rather than something each test remembers."""
        from llm_council.performance import integration

        first = tmp_path / "first.jsonl"
        monkeypatch.setenv("LLM_COUNCIL_PERFORMANCE_STORE", str(first))
        integration._reset_tracker_singleton()
        assert integration.get_tracker().store_path == first

        second = tmp_path / "second.jsonl"
        monkeypatch.setenv("LLM_COUNCIL_PERFORMANCE_STORE", str(second))
        integration._reset_tracker_singleton()
        assert integration.get_tracker().store_path == second


class TestTheRealStoreIsUnreachableFromTests:
    def test_no_test_can_write_under_the_real_home(self):
        """The guard. If the autouse fixture is removed, renamed, or stops
        working, this fails — which is the difference between a convention and
        an invariant."""
        from llm_council.performance import integration

        resolved = integration.resolve_store_path().resolve()
        assert REAL_HOME not in resolved.parents, (
            f"the performance store resolves to {resolved}, which is inside the "
            f"real HOME ({REAL_HOME}). A test run must never append to an "
            f"operator's data — see #693, where 1,868 fixture rows made a "
            f"working cost pipeline look broken."
        )

    def test_the_autouse_fixture_is_in_effect(self, tmp_path):
        """The redirect points at THIS test's own tmp_path, not at a shared
        location that would merely move the pollution.

        Asserted as an exact path rather than by sniffing for "pytest" in the
        string: the fixture and this test receive the same per-test `tmp_path`,
        so equality is available and a substring check would have passed under
        a custom `--basetemp` while proving nothing.
        """
        from llm_council.performance import integration

        assert integration.resolve_store_path() == tmp_path / "performance_metrics.jsonl"

    def test_a_real_persist_lands_in_the_isolated_store(self):
        """End to end: the thing the seven unpatched call sites in
        `test_adr041_verification_telemetry.py` were doing now lands in the
        temporary store instead of the operator's file."""
        from llm_council.performance import integration

        written = integration.persist_session_performance_data(
            session_id="issue693",
            model_statuses={"test/model-a": {"status": "ok", "latency_ms": 1500}},
            aggregate_rankings={"test/model-a": {"borda_score": 0.75}},
        )
        assert written == 1

        store = integration.resolve_store_path()
        assert store.exists(), "the isolated store was not created"
        rows = [json.loads(line) for line in store.read_text().splitlines() if line.strip()]
        assert any(r.get("session_id") == "issue693" for r in rows)


class TestTheOperatorCleanupIsDocumentedNotAutomatic:
    """#693 is explicit that no migration may rewrite an operator's data. The
    one-liner is documentation; this only checks it is documented, because a
    tool that edits someone's file on upgrade is the thing we refuse to ship."""

    def test_the_cleanup_recipe_is_in_the_docs(self):
        repo_root = Path(__file__).resolve().parents[1]
        guide = repo_root / "docs/guides/performance-store.md"
        assert guide.is_file(), (
            "#693 requires a documented one-liner for operators to strip "
            "historical test/* rows from their own file"
        )
        text = guide.read_text()
        assert "test/" in text
        assert "jq" in text or "grep" in text, "no runnable recipe found"
        assert "never" in text.lower(), (
            "the guide must state that council never rewrites the operator's "
            "file itself — #693 refuses an automatic migration"
        )


@pytest.mark.parametrize(
    "path_env",
    ["", "   "],
)
def test_a_blank_env_var_falls_back_to_the_default_not_to_cwd(monkeypatch, path_env):
    """An empty string is a configuration mistake, not a request to write to
    the process's current directory — which for a test run is the repo."""
    from llm_council.performance import integration

    monkeypatch.setenv("LLM_COUNCIL_PERFORMANCE_STORE", path_env)
    resolved = integration.resolve_store_path()
    assert resolved.name == "performance_metrics.jsonl"
    assert resolved != Path("performance_metrics.jsonl")
    assert resolved.is_absolute()
