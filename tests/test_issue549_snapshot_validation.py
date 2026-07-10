"""#549: `run_verification` validates snapshot_id at its own boundary.

Both production callers (CLI, MCP) build a `VerifyRequest`, whose Pydantic
field-validator rejects a malformed `snapshot_id` at construction — so the
HTTP/CLI/MCP paths are already covered. `run_verification` accepts the request object directly. It was NOT a live hole —
`VerificationContextManager` already re-validates before the first git argv call —
but that guarantee was implicit and positional. #549 makes `run_verification`
validate at its own entry, so it fails fast and stays correct even if the context
manager moves. These tests neuter that downstream check to prove the boundary
guard stands on its own.

Shell injection is already precluded (argv arrays; zero `shell=True`). The
residual class is ARGUMENT injection, load-bearing once P3.1 adds pathspec-style
`git ... -- <paths>` calls.
"""

import pytest

from llm_council.verification.context import InvalidSnapshotError
from llm_council.verification.schemas import VerifyRequest
from llm_council.verification.transcript import create_transcript_store


@pytest.mark.parametrize(
    "bad",
    ["--upload-pack=evil", "-x", "HEAD; rm -rf", "not a sha", "zzz$(whoami)"],
)
def test_run_verification_rejects_unvalidated_snapshot(bad, tmp_path, monkeypatch):
    """A request that skipped Pydantic validation must still be rejected."""
    import asyncio

    # model_construct bypasses field validators — the defense-in-depth case.
    req = VerifyRequest.model_construct(snapshot_id=bad, tier="balanced", target_paths=None)
    store = create_transcript_store(base_path=tmp_path)

    import llm_council.verification.context as ctx
    import llm_council.verification.api as api_mod

    # Neuter the DOWNSTREAM (context-manager) validation so this asserts the
    # boundary guard in run_verification specifically, not the pre-existing one.
    monkeypatch.setattr(ctx, "validate_snapshot_id", lambda s: True)

    with pytest.raises(InvalidSnapshotError):
        asyncio.run(api_mod.run_verification(req, store))


def test_valid_snapshot_is_not_rejected(tmp_path, monkeypatch):
    """A well-formed 40-hex SHA passes the boundary check (fails later, elsewhere)."""
    from llm_council.verification.context import validate_snapshot_id

    # The boundary check itself accepts a valid SHA. (Full run_verification needs
    # network + a real commit; the unit under test here is only the guard.)
    assert validate_snapshot_id("a" * 40) is True
