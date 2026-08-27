"""#642: hold the mypy error count down while the debt is burned off.

The CI "Type Check" job runs `mypy ... || echo "(non-blocking)"`, so it is green
whatever mypy says. That is a deliberate choice while ~100 pre-existing errors
exist — a blocking gate would red every PR for faults it didn't introduce — but
it means CI green does not imply type-clean, and nothing stops the count
climbing.

This is the intermediate ratchet #642 asks for at step 4, applied before the
count reaches zero: new type errors fail here, existing ones don't. When you
fix some, lower ``MAX_MYPY_ERRORS`` in the same PR — the number only ever goes
down, and the final decrement to 0 is when the `|| echo` comes out of CI.

Runs the same invocation as `make typecheck`, so the two cannot drift.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Measured on master 2026-08-27 after the #642 mechanical pass
# (implicit-Optional codemod, yaml stubs, six missing annotations, two dead
# guards). Was 97 before it. LOWER THIS when you fix more; never raise it.
MAX_MYPY_ERRORS = 73

_SUMMARY = re.compile(r"Found (\d+) errors? in \d+ files?")


def _run_mypy() -> str:
    return subprocess.run(
        [sys.executable, "-m", "mypy", "src/llm_council", "--ignore-missing-imports"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout


@pytest.mark.slow
def test_mypy_error_count_does_not_regress():
    if shutil.which("mypy") is None:
        try:
            import mypy  # noqa: F401
        except ImportError:
            pytest.skip("mypy not installed")

    output = _run_mypy()
    match = _SUMMARY.search(output)
    if match is None:
        # "Success: no issues found" — the goal state. Fail loudly so whoever
        # gets there also removes the `|| echo` from CI and deletes this file.
        assert "Success" in output, f"could not parse mypy output:\n{output[-2000:]}"
        pytest.fail(
            "mypy is clean. Finish #642: drop the `|| echo` fallback from the CI "
            "Type Check job so it actually blocks, then delete this ratchet."
        )

    count = int(match.group(1))
    assert count <= MAX_MYPY_ERRORS, (
        f"mypy errors rose to {count}, above the #642 ratchet of "
        f"{MAX_MYPY_ERRORS}. Fix the new errors — do not raise the ceiling.\n"
        f"Run `make typecheck` to see them.\n\n{output[-4000:]}"
    )

    if count < MAX_MYPY_ERRORS:
        pytest.fail(
            f"mypy errors are down to {count}, below the ratchet of "
            f"{MAX_MYPY_ERRORS}. Lower MAX_MYPY_ERRORS to {count} in this file "
            "so the improvement is locked in."
        )
