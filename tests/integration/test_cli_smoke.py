import subprocess
import sys
import os
import pytest


def test_query_cli_parameter_parity():
    """
    Smoke test to ensure the CLI entry point can actually invoke the council
    without signature or TypeError regressions.

    This executes 'query.py' in a subprocess to bypass any in-memory mocking
    that might hide signature regressions.
    """
    # Use 'uv run' to ensure we have the correct environment
    # We use a dummy query and --help or similar if we want to avoid LLM calls,
    # but for a REAL signature check, we need it to reach the function call.
    # We'll use a mocked env or a known fail-fast path.

    # Actually, running the help is safe and checks argument parsing,
    # but doesn't check the internal call.

    # Let's try to run a query that we know will fail auth but pass parameter validation.
    result = subprocess.run(
        [sys.executable, "query.py", "Test query", "--confidence", "quick"],
        capture_output=True,
        text=True,
        env={**os.environ, "OPENROUTER_API_KEY": "sk-invalid-test-key"},
    )

    # We EXPECT a failure due to the invalid key, but we should NOT see a TypeError
    # about 'run_full_council' or 'unexpected keyword argument'.

    stderr = result.stderr
    stdout = result.stdout

    # Check for the specific TypeError we found in BUG-023
    assert "TypeError: run_full_council() got an unexpected keyword argument" not in stderr
    assert "TypeError: run_full_council() got an unexpected keyword argument" not in stdout

    # Check for structure mismatch (unpacking error)
    assert "not enough values to unpack" not in stderr
    assert "too many values to unpack" not in stderr

    print("CLI Smoke Test Passed: Parameters and Signature validated.")


if __name__ == "__main__":
    test_query_cli_parameter_parity()
