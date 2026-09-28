"""#656, #614, #630 — three controls that degraded silently.

* #656: the HTTP API token was compared with ``!=``, which short-circuits on
  the first differing byte. ``webhooks/hmac_auth.py`` already does this right.
* #614: query hashing fell back to a PUBLISHED default secret when
  ``LLM_COUNCIL_HASH_SECRET`` was unset. With a known key, anyone holding the
  store can confirm a guessed query is in it: the dictionary attack the HMAC
  exists to prevent. The fallback is now a random per-install secret,
  persisted 0600 beside the bias store. If it cannot be created, hashing is
  skipped rather than done with a known key.
* #630: the legacy verdict patterns counted "NOT RECOMMENDED" as both approve
  and reject. Worse, and not in the ticket: "NOT APPROVED" and "NOT ACCEPTED"
  matched ONLY the approve patterns, so a rejection read as PASS at 0.80.
"""

import ast
import os
import pathlib
import stat
from unittest.mock import patch

import pytest

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "llm_council"


class TestTheApiTokenIsComparedInConstantTime:
    def test_verify_token_uses_compare_digest(self):
        tree = ast.parse((SRC / "http_server.py").read_text())
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "verify_token"
        )
        calls = {
            f"{c.func.value.id}.{c.func.attr}"
            for c in ast.walk(fn)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and isinstance(c.func.value, ast.Name)
        }
        assert "hmac.compare_digest" in calls
        comparisons = [n for n in ast.walk(fn) if isinstance(n, ast.Compare)]
        assert not any(
            isinstance(op, (ast.Eq, ast.NotEq)) for c in comparisons for op in c.ops
        ), "the token must not be compared with == or !="

    def test_a_wrong_token_is_still_rejected_and_a_right_one_accepted(self):
        from fastapi.testclient import TestClient

        with patch.dict(os.environ, {"LLM_COUNCIL_API_TOKEN": "secret-token"}):
            from llm_council.http_server import app

            client = TestClient(app)
            bad = client.post(
                "/v1/council/run",
                json={"prompt": "x"},
                headers={"Authorization": "Bearer secret-tokeX"},
            )
            assert bad.status_code == 401

    @pytest.mark.parametrize("presented", ["s\u00e9cret-token", "secret-token\u2603", ""])
    def test_a_non_ascii_or_empty_token_is_rejected_not_raised(self, presented, monkeypatch):
        """compare_digest raises TypeError on a non-ASCII str, which would turn
        a bad token into a 500. Called directly: an HTTP client will not even
        send a non-ASCII header."""
        import asyncio

        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        from llm_council.http_server import verify_token

        monkeypatch.setenv("LLM_COUNCIL_API_TOKEN", "secret-token")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=presented)
        with pytest.raises(HTTPException) as err:
            asyncio.run(verify_token(creds))
        assert err.value.status_code == 401

    def test_the_right_token_is_accepted(self, monkeypatch):
        import asyncio

        from fastapi.security import HTTPAuthorizationCredentials

        from llm_council.http_server import verify_token

        monkeypatch.setenv("LLM_COUNCIL_API_TOKEN", "secret-token")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret-token")
        assert asyncio.run(verify_token(creds)) is None


class TestTheHashSecretIsNeverAKnownDefault:
    @pytest.fixture
    def secret_file(self, tmp_path, monkeypatch):
        path = tmp_path / "hash_secret"
        monkeypatch.setenv("LLM_COUNCIL_HASH_SECRET_FILE", str(path))
        monkeypatch.delenv("LLM_COUNCIL_HASH_SECRET", raising=False)
        return path

    def test_no_module_level_secret_survives(self):
        import llm_council.bias_persistence as bp

        assert not hasattr(bp, "BIAS_HASH_SECRET")
        assert "default-dev-secret" not in (SRC / "bias_persistence.py").read_text()

    def test_an_unset_secret_generates_a_private_per_install_one(self, secret_file):
        from llm_council.bias_persistence import ConsentLevel, hash_query_if_enabled

        first = hash_query_if_enabled("q", ConsentLevel.RESEARCH)
        assert secret_file.exists()
        assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600
        assert len(secret_file.read_text().strip()) >= 64
        # Persisted, so grouping across sessions still works.
        assert hash_query_if_enabled("q", ConsentLevel.RESEARCH) == first

    def test_two_installs_hash_the_same_query_differently(self, tmp_path, monkeypatch):
        from llm_council.bias_persistence import ConsentLevel, hash_query_if_enabled

        monkeypatch.delenv("LLM_COUNCIL_HASH_SECRET", raising=False)
        hashes = []
        for name in ("one", "two"):
            monkeypatch.setenv("LLM_COUNCIL_HASH_SECRET_FILE", str(tmp_path / name))
            hashes.append(hash_query_if_enabled("q", ConsentLevel.RESEARCH))
        assert hashes[0] != hashes[1]

    def test_an_explicit_secret_still_wins(self, secret_file, monkeypatch):
        from llm_council.bias_persistence import ConsentLevel, hash_query_if_enabled

        monkeypatch.setenv("LLM_COUNCIL_HASH_SECRET", "configured")
        hash_query_if_enabled("q", ConsentLevel.RESEARCH)
        assert not secret_file.exists()

    def test_an_uncreatable_secret_skips_hashing_rather_than_using_a_known_key(
        self, tmp_path, monkeypatch
    ):
        from llm_council.bias_persistence import ConsentLevel, hash_query_if_enabled

        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x")
        monkeypatch.delenv("LLM_COUNCIL_HASH_SECRET", raising=False)
        monkeypatch.setenv("LLM_COUNCIL_HASH_SECRET_FILE", str(blocker / "hash_secret"))
        assert hash_query_if_enabled("q", ConsentLevel.RESEARCH) is None

    def test_the_test_suite_never_resolves_the_secret_under_the_real_home(self):
        """#693's lesson: a test must not write into the operator's HOME."""
        from llm_council.bias_persistence import _hash_secret_path

        real_home = pathlib.Path(os.path.expanduser("~")).resolve()
        assert real_home not in _hash_secret_path().resolve().parents


class TestNegatedVerdictsAreRejections:
    @pytest.mark.parametrize(
        "text",
        [
            "The change is NOT RECOMMENDED.",
            "Verdict: NOT APPROVED.",
            "This is not accepted by the council.",
            "It does NOT PASS review.",
            "NOT  APPROVED",  # extra whitespace
        ],
    )
    def test_a_negated_approval_is_a_fail(self, text):
        from llm_council.verification.verdict_extractor import extract_verdict_from_synthesis

        verdict, _confidence = extract_verdict_from_synthesis({"response": text})
        assert verdict == "fail", f"{text!r} read as {verdict}"

    def test_not_recommended_counts_once(self):
        """The ticket's case: it used to increment BOTH counts."""
        from llm_council.verification.verdict_extractor import extract_verdict_from_synthesis

        verdict, confidence = extract_verdict_from_synthesis({"response": "NOT RECOMMENDED"})
        assert verdict == "fail"
        assert confidence == pytest.approx(0.80)

    @pytest.mark.parametrize("text", ["APPROVED", "Recommended for merge.", "PASSED"])
    def test_a_plain_approval_still_passes(self, text):
        from llm_council.verification.verdict_extractor import extract_verdict_from_synthesis

        assert extract_verdict_from_synthesis({"response": text})[0] == "pass"


class TestGateRound1ConsentFailsClosed:
    """Council gate on #715, round 1: two pre-existing privacy defects in the
    module this PR hardens. ConsentLevel.OFF ("no telemetry or storage")
    still wrote records, and an unreadable or unknown consent setting fell
    back to LOCAL_ONLY, i.e. to storing."""

    @pytest.fixture
    def store(self, tmp_path, monkeypatch):
        from llm_council import bias_persistence as bp

        path = tmp_path / "bias_metrics.jsonl"
        monkeypatch.setattr(bp, "_get_bias_store_path", lambda: path)
        monkeypatch.setattr(bp, "_get_bias_persistence_enabled", lambda: True)
        return bp, path

    @staticmethod
    def _persist(bp):
        return bp.persist_session_bias_data(
            "s1",
            [{"model": "a/one", "response": "x"}],
            [
                {
                    "model": "b/two",
                    "parsed_ranking": {"ranking": ["Response A"], "scores": {"Response A": 7}},
                }
            ],
            {"Response A": {"model": "a/one", "display_index": 0}},
        )

    def test_consent_off_writes_nothing(self, store, monkeypatch):
        bp, path = store
        monkeypatch.setattr(bp, "_get_bias_consent_level", lambda: 0)
        assert self._persist(bp) == 0
        assert not path.exists()

    @pytest.mark.parametrize("level", [99, -1])
    def test_an_invalid_consent_level_fails_closed(self, store, monkeypatch, level):
        bp, path = store
        monkeypatch.setattr(bp, "_get_bias_consent_level", lambda: level)
        assert self._persist(bp) == 0
        assert not path.exists()

    def test_an_unreadable_config_resolves_to_off(self, monkeypatch):
        from llm_council import bias_persistence as bp

        def boom():
            raise RuntimeError("config unreadable")

        monkeypatch.setattr(bp, "get_config", boom)
        assert bp._get_bias_consent_level() == 0

    def test_an_unknown_consent_string_resolves_to_off(self, monkeypatch):
        from types import SimpleNamespace

        from llm_council import bias_persistence as bp

        cfg = SimpleNamespace(
            evaluation=SimpleNamespace(bias=SimpleNamespace(consent_level="LOCAL_ONYL"))
        )
        monkeypatch.setattr(bp, "get_config", lambda: cfg)
        assert bp._get_bias_consent_level() == 0

    def test_local_only_still_writes(self, store, monkeypatch):
        bp, path = store
        monkeypatch.setattr(bp, "_get_bias_consent_level", lambda: 1)
        assert self._persist(bp) == 1

    def test_the_store_is_private(self, store, monkeypatch):
        bp, path = store
        monkeypatch.setattr(bp, "_get_bias_consent_level", lambda: 1)
        self._persist(bp)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    @pytest.mark.parametrize("line", ["3", "[1, 2]", '"text"', "null"])
    def test_a_non_object_line_does_not_crash_the_reader(self, store, monkeypatch, line):
        bp, path = store
        monkeypatch.setattr(bp, "_get_bias_consent_level", lambda: 1)
        self._persist(bp)
        with path.open("a") as handle:
            handle.write(line + "\n")
        assert len(bp.read_bias_records(path)) == 1

    @pytest.mark.parametrize("bad", ["N/A", float("nan"), 10**400, True])
    def test_a_malformed_score_does_not_abort_persistence(self, bad):
        from llm_council.bias_persistence import create_bias_records_from_session

        records = create_bias_records_from_session(
            "s1",
            [{"model": "a/one", "response": "x"}],
            [
                {
                    "model": "b/two",
                    "parsed_ranking": {"ranking": ["Response A"], "scores": {"Response A": bad}},
                }
            ],
            {"Response A": {"model": "a/one", "display_index": 0}},
        )
        assert len(records) == 1


class TestGateRound1SecretFile:
    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_HASH_SECRET", raising=False)
        path = tmp_path / "hash_secret"
        monkeypatch.setenv("LLM_COUNCIL_HASH_SECRET_FILE", str(path))
        return path

    def test_a_symlinked_secret_is_refused(self, env, tmp_path):
        from llm_council.bias_persistence import _resolve_hash_secret

        target = tmp_path / "attacker_chosen"
        target.write_text("a" * 64)
        env.symlink_to(target)
        assert _resolve_hash_secret() is None

    def test_a_group_or_world_writable_secret_is_refused(self, env):
        from llm_council.bias_persistence import _resolve_hash_secret

        env.write_text("b" * 64)
        env.chmod(0o666)
        assert _resolve_hash_secret() is None

    def test_an_empty_secret_file_is_regenerated(self, env):
        from llm_council.bias_persistence import _resolve_hash_secret

        env.write_text("")
        env.chmod(0o600)
        secret = _resolve_hash_secret()
        assert secret and len(secret) >= 64
        assert env.read_text().strip() == secret

    def test_a_too_short_configured_secret_is_refused(self, env, monkeypatch):
        from llm_council.bias_persistence import _resolve_hash_secret

        monkeypatch.setenv("LLM_COUNCIL_HASH_SECRET", "x")
        assert _resolve_hash_secret() is None


class TestGateRound2:
    """Council gate on #715, round 2: the round-1 fixes were right on the
    create path and wrong on the paths an upgraded install actually takes."""

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_HASH_SECRET", raising=False)
        path = tmp_path / "hash_secret"
        monkeypatch.setenv("LLM_COUNCIL_HASH_SECRET_FILE", str(path))
        return path

    @pytest.mark.parametrize("mode", [0o644, 0o640, 0o604])
    def test_a_group_or_world_readable_secret_is_refused(self, env, mode):
        # Readable is as bad as writable: a reader can confirm guessed queries.
        from llm_council.bias_persistence import _resolve_hash_secret

        env.write_text("c" * 64)
        env.chmod(mode)
        assert _resolve_hash_secret() is None
        assert env.read_text() == "c" * 64  # never silently replaced

    def test_a_too_short_persisted_secret_is_refused(self, env):
        from llm_council.bias_persistence import _resolve_hash_secret

        env.write_text("x\n")
        env.chmod(0o600)
        assert _resolve_hash_secret() is None

    def test_a_private_persisted_secret_is_used(self, env):
        from llm_council.bias_persistence import _resolve_hash_secret

        env.write_text("d" * 64 + "\n")
        env.chmod(0o600)
        assert _resolve_hash_secret() == "d" * 64

    def test_a_pre_existing_permissive_store_is_tightened(self, tmp_path):
        from llm_council.bias_persistence import BiasMetricRecord, append_bias_records

        path = tmp_path / "bias_metrics.jsonl"
        path.write_text("")
        path.chmod(0o644)  # what every pre-#715 install left behind
        append_bias_records([BiasMetricRecord(session_id="s", reviewer_id="r")], path)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_a_symlinked_store_is_not_written_through(self, tmp_path):
        from llm_council.bias_persistence import BiasMetricRecord, append_bias_records

        target = tmp_path / "elsewhere.jsonl"
        target.write_text("")
        path = tmp_path / "bias_metrics.jsonl"
        path.symlink_to(target)
        with pytest.raises(OSError):
            append_bias_records([BiasMetricRecord(session_id="s", reviewer_id="r")], path)
        assert target.read_text() == ""
