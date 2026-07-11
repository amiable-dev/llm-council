"""Coverage clamp + layer-1 reason-set ack (#556, ADR-053 Open Question 1).

A `pass` may not be returned over a changed-or-explicit file the council did not
review. The clamp turns the #555 receipt's omissions into an
`unclear(incomplete_coverage)` verdict — UNLESS acknowledged.

Layer 1 (this PR): `LLM_COUNCIL_COVERAGE_ACK_REASONS` — an operator reason-set
(default `binary,generated,vendored,too_large,ignored,noise`), so the clamp fires
only on the surprising residue (`non-text` = the #542 unlisted-language bug,
`not_found`, `truncated`, `denied_secret` of a changed file). Explicit-origin
omissions clamp regardless of reason — a named path is a caller contract.

Decisions (2026-07-11): non-text clamps; the clamp yields
`unclear(incomplete_coverage)`, not a hard error (that is the `fail` policy).
Layers 2/3 (committed baseline, per-call list) are deferred.
"""

import pytest

from llm_council.verification import coverage


def _cov(*omitted, reviewed=("a.py",)):
    return {
        "reviewed": list(reviewed),
        "omitted": list(omitted),
        "explicit_omitted": any(o["origin"] == "explicit" for o in omitted),
    }


def _om(path, reason, origin="discovered"):
    return {"path": path, "reason": reason, "origin": origin}


class TestPolicyAndAckParsing:
    def test_policy_default_is_warn_during_rollout(self, monkeypatch):
        # #556 ships opt-in: default warn = byte-identical verdicts. Flips to
        # clamp (#557) after telemetry — a one-line change to _DEFAULT_POLICY.
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        assert coverage.coverage_policy() == "warn"

    @pytest.mark.parametrize("val,expected", [("clamp", "clamp"), ("fail", "fail"), ("x", "warn")])
    def test_policy_values(self, monkeypatch, val, expected):
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", val)
        assert coverage.coverage_policy() == expected

    def test_default_ack_reasons(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_ACK_REASONS", raising=False)
        acks = coverage.coverage_ack_reasons()
        assert {"binary", "generated", "vendored", "too_large", "ignored", "noise"} == set(acks)
        assert "non-text" not in acks and "not_found" not in acks

    def test_ack_reasons_override(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_ACK_REASONS", "binary, non-text")
        assert coverage.coverage_ack_reasons() == frozenset({"binary", "non-text"})

    def test_ack_reasons_empty_clamps_everything(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_ACK_REASONS", "")
        assert coverage.coverage_ack_reasons() == frozenset()


class TestClampDecision:
    @pytest.fixture(autouse=True)
    def _defaults(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_ACK_REASONS", raising=False)

    def test_non_text_clamps_a_pass(self):
        cov = _cov(_om("main.zig", "non-text"))
        clampers = coverage.coverage_clamp_decision(
            "pass", cov, "clamp", coverage.coverage_ack_reasons()
        )
        assert clampers and clampers[0]["path"] == "main.zig"

    def test_binary_is_acked_by_default(self):
        cov = _cov(_om("logo.png", "binary"))
        assert (
            coverage.coverage_clamp_decision("pass", cov, "clamp", coverage.coverage_ack_reasons())
            is None
        )

    def test_generated_vendored_ignored_too_large_noise_acked(self):
        cov = _cov(
            _om("gen.js", "generated"),
            _om("vendor/x.js", "vendored"),
            _om("build/o", "ignored"),
            _om("big.txt", "too_large"),
            _om("i.svg", "noise"),
        )
        assert (
            coverage.coverage_clamp_decision("pass", cov, "clamp", coverage.coverage_ack_reasons())
            is None
        )

    def test_explicit_omission_clamps_regardless_of_reason(self):
        # a caller NAMED a binary; that is a contract, so it clamps even though
        # `binary` is in the default ack set.
        cov = _cov(_om("logo.png", "binary", origin="explicit"))
        clampers = coverage.coverage_clamp_decision(
            "pass", cov, "clamp", coverage.coverage_ack_reasons()
        )
        assert clampers and clampers[0]["origin"] == "explicit"

    def test_not_found_and_truncated_and_secret_clamp(self):
        for reason in ("not_found", "truncated", "denied_secret"):
            cov = _cov(_om("x", reason))
            assert coverage.coverage_clamp_decision(
                "pass", cov, "clamp", coverage.coverage_ack_reasons()
            ), reason

    def test_fail_verdict_is_never_clamped(self):
        cov = _cov(_om("main.zig", "non-text"))
        assert (
            coverage.coverage_clamp_decision("fail", cov, "clamp", coverage.coverage_ack_reasons())
            is None
        )

    def test_warn_policy_never_clamps(self):
        cov = _cov(_om("main.zig", "non-text"))
        assert (
            coverage.coverage_clamp_decision("pass", cov, "warn", coverage.coverage_ack_reasons())
            is None
        )

    def test_full_coverage_does_not_clamp(self):
        cov = _cov(reviewed=("a.py", "b.py"))
        assert (
            coverage.coverage_clamp_decision("pass", cov, "clamp", coverage.coverage_ack_reasons())
            is None
        )

    def test_none_coverage_is_safe(self):
        assert coverage.coverage_clamp_decision("pass", None, "clamp", frozenset()) is None


class TestGateWarnGuard:
    def test_gate_allows_warn_while_it_is_the_default(self, monkeypatch):
        # Pre-flip (_DEFAULT_POLICY=warn): a gate in warn is the status quo, not a
        # foot-gun, so it is NOT refused.
        monkeypatch.setattr(coverage, "_DEFAULT_POLICY", "warn")
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", "warn")
        assert coverage.gate_rejects_warn() is False

    def test_gate_refuses_explicit_warn_after_the_flip(self, monkeypatch):
        # Post-flip (_DEFAULT_POLICY=clamp): explicit warn is a deliberate
        # downgrade of a gate — refused.
        monkeypatch.setattr(coverage, "_DEFAULT_POLICY", "clamp")
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", "warn")
        assert coverage.gate_rejects_warn() is True

    def test_run_gate_returns_nonzero_when_warn_rejected(self, monkeypatch, capsys):
        from llm_council.cli import run_gate

        monkeypatch.setattr(coverage, "_DEFAULT_POLICY", "clamp")
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", "warn")
        rc = run_gate(
            snapshot="a" * 40,
            file_paths=None,
            confidence_threshold=0.7,
            rubric_focus=None,
            output_format="text",
            tier="balanced",
        )
        err = capsys.readouterr()
        assert rc != 0 and "warn" in (err.out + err.err).lower()


class TestReceiptFeedsClamp:
    """Integration: the real #555 receipt drives the clamp (no live council)."""

    def test_real_receipt_with_a_zig_clamps(self, tmp_path, monkeypatch):
        import asyncio
        import subprocess

        from llm_council.verification import file_ops

        repo = tmp_path / "r"
        repo.mkdir()

        def g(*a):
            subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)

        g("init", "-q", ".")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        (repo / "README.md").write_text("root\n")
        g("add", "-A")
        g("commit", "-qm", "root")
        (repo / "app.py").write_text("x=1\n")
        (repo / "main.zig").write_text("const x=1;\n")  # non-text in allowlist mode
        g("add", "-A", "-f")
        g("commit", "-qm", "work")
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        ).stdout.strip()
        monkeypatch.setattr(file_ops, "_cached_git_root", str(repo))
        monkeypatch.chdir(repo)
        monkeypatch.delenv("LLM_COUNCIL_FILE_SELECTION", raising=False)  # allowlist

        _c, meta = asyncio.run(
            file_ops._fetch_files_for_verification_async_with_metadata(sha, None)
        )
        cov = meta["coverage"]
        assert "app.py" in cov["reviewed"]
        # main.zig was silently dropped (the #542 bug); the clamp catches it.
        clampers = coverage.coverage_clamp_decision(
            "pass", cov, "clamp", coverage.coverage_ack_reasons()
        )
        assert clampers and any(c["path"] == "main.zig" for c in clampers)


class TestPipelineAppliesClamp:
    """Full run_verification: a `pass` over a clamping coverage → unclear(incomplete_coverage)."""

    def _run(self, monkeypatch, coverage_dict, base_verdict="pass"):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_council.verification import api
        from llm_council.verification.schemas import VerifyRequest

        # NB: the caller controls LLM_COUNCIL_COVERAGE_POLICY via its own
        # monkeypatch; do not clear it here (monkeypatch isolates per test).
        req = VerifyRequest(snapshot_id="a" * 40, tier="balanced")
        store = MagicMock()

        render_info = {
            "kept": [],
            "warnings": [],
            "chars_rendered": 0,
            "chars_submitted": 0,
            "expansion": {"coverage": coverage_dict},
        }
        with (
            patch.object(
                api,
                "_build_verification_prompt",
                new_callable=AsyncMock,
                return_value=("prompt", render_info),
            ),
            patch.object(
                api,
                "stage1_collect_responses_with_status",
                new_callable=AsyncMock,
                return_value=([{"model": "m", "response": "ok"}], {}, {}),
            ),
            patch.object(
                api, "stage2_collect_rankings", new_callable=AsyncMock, return_value=([], {}, {})
            ),
            patch.object(
                api,
                "stage3_synthesize_final",
                new_callable=AsyncMock,
                return_value=({"response": "ok"}, {}, None),
            ),
            patch.object(api, "calculate_aggregate_rankings", return_value=[]),
            patch.object(
                api,
                "build_verification_result",
                return_value={
                    "verdict": base_verdict,
                    "confidence": 0.9,
                    "confidence_calibrated": 0.9,
                    "rubric_scores": {},
                    "blocking_issues": [],
                    "rationale": "ok",
                    "diagnostics": {},
                },
            ),
            patch.object(api, "VerificationContextManager") as ctx,
        ):
            c = MagicMock()
            c.context_id = "t"
            ctx.return_value.__enter__ = MagicMock(return_value=c)
            ctx.return_value.__exit__ = MagicMock(return_value=False)
            return asyncio.run(api.run_verification(req, store))

    def test_pass_over_non_text_omission_becomes_unclear(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", "clamp")
        cov = {"reviewed": ["a.py"], "omitted": [_om("main.zig", "non-text")]}
        result = self._run(monkeypatch, cov)
        assert result["verdict"] == "unclear"
        assert result["unclear_reason"] == "incomplete_coverage"
        assert result["exit_code"] == 2
        assert any(c["path"] == "main.zig" for c in result["coverage"]["clamped"])

    def test_pass_over_acked_binary_stays_pass(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_COVERAGE_POLICY", "clamp")
        cov = {"reviewed": ["a.py"], "omitted": [_om("logo.png", "binary")]}
        result = self._run(monkeypatch, cov)
        assert result["verdict"] == "pass"
        assert "clamped" not in (result.get("coverage") or {})

    def test_warn_default_leaves_pass_untouched(self, monkeypatch):
        # default (unset) is warn during rollout ⇒ no clamp, byte-identical verdict
        monkeypatch.delenv("LLM_COUNCIL_COVERAGE_POLICY", raising=False)
        cov = {"reviewed": ["a.py"], "omitted": [_om("main.zig", "non-text")]}
        result = self._run(monkeypatch, cov)
        assert result["verdict"] == "pass"
        assert result["coverage"]["policy"] == "warn"
