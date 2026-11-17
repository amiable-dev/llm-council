"""Hash-pinned requirement files must match uv.lock.

The Railway image and the ClusterFuzzLite build install dependencies with
``pip install --require-hashes`` from files exported from ``uv.lock``. An
export that lags the lockfile would ship versions nobody reviewed, so this
fails until the file is regenerated with the command in the message.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

EXPORTS = {
    "deploy/railway/requirements.txt": ["--extra", "http"],
    ".clusterfuzzlite/requirements.txt": [],
}


def _pins(text: str) -> list[str]:
    """Requirement and hash lines only: the header comment names the command."""
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


@pytest.mark.parametrize("path", sorted(EXPORTS))
def test_export_matches_the_lockfile(path: str) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    args = ["export", "--locked", "--no-dev", "--no-emit-project", "--hashes", *EXPORTS[path]]
    result = subprocess.run([uv, *args], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    command = "uv " + " ".join(args) + f" -o {path}"
    assert _pins((ROOT / path).read_text()) == _pins(result.stdout), (
        f"{path} is out of date with uv.lock. Regenerate it with: {command}"
    )


@pytest.mark.parametrize("path", sorted(EXPORTS))
def test_every_requirement_carries_a_hash(path: str) -> None:
    text = (ROOT / path).read_text()
    names = [line for line in text.splitlines() if line and line[0].isalnum()]
    assert names, f"{path} lists no requirements"
    for line in names:
        assert line.rstrip().endswith("\\"), f"{path}: no hash follows {line!r}"
