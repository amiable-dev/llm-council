"""#690 — the tier pools must have exactly ONE definition, and it must ship.

## The defect this file exists to prevent

Before this change the pools were written out three times:

* `llm_council.yaml` — the repo's config, which is **not in the wheel**
* `unified_config.py::TierConfig.ensure_default_pools` — fills any tier the
  loaded YAML omits
* `tier_contract.py::_DEFAULT_TIER_MODEL_POOLS` — "used when config isn't
  loaded yet", and re-exported as the public `TIER_MODEL_POOLS`

#685 updated the first one only. The result was that every published claim
about v0.48.0's pools was false for anyone running the wheel without a
hand-copied config — which is the default state, since the file neither ships
nor is created by `make setup`. `gpt-5.6-luna` stayed in `quick` at 35.3s
against a 30s budget; `gemini-3.1-pro-preview` stayed in `high` and
`reasoning` against the ADR-027 rule that previews audition in `frontier`;
and `frontier` never received the four 2026-09 flagships it was supposed to
be auditioning.

`tests/test_tier_pool_hygiene.py` did not catch any of it, because it parsed
`llm_council.yaml` — the one copy that was correct. Every invariant it
enforces was unenforced on the path users actually take.

## What is asserted here

Not "the copies agree" — that only detects drift after the fact, and needs a
test per copy. **There is one definition**, it is package data so it ships,
and the modules that used to hold literals now read it. The AST check is the
load-bearing one: it makes a re-added literal fail, which the equality checks
alone would not do the moment someone adds a fourth copy somewhere new.
"""

import ast
import contextlib
import pathlib
import re

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGED_DEFAULTS = REPO_ROOT / "src/llm_council/models/default_pools.yaml"
REPO_CONFIG = REPO_ROOT / "llm_council.yaml"
TIER_CONTRACT_SRC = REPO_ROOT / "src/llm_council/tier_contract.py"
UNIFIED_CONFIG_SRC = REPO_ROOT / "src/llm_council/unified_config.py"

EXPECTED_TIERS = {"quick", "balanced", "high", "reasoning", "frontier"}

# `provider/model`, the OpenRouter id form every pool entry uses. Deliberately
# narrow: it must match a model id and must NOT match a path fragment like
# "src/llm_council" or a URL, so the AST check reports real regressions only.
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._:-]*$")


@pytest.fixture(scope="module")
def packaged():
    assert PACKAGED_DEFAULTS.is_file(), (
        f"{PACKAGED_DEFAULTS} is the single source of truth for the tier pools "
        "and must exist"
    )
    return yaml.safe_load(PACKAGED_DEFAULTS.read_text())["pools"]


class TestThereIsOneDefinitionAndItShips:
    def test_the_packaged_file_defines_every_tier(self, packaged):
        assert set(packaged) == EXPECTED_TIERS
        for tier, body in packaged.items():
            assert body.get("models"), f"{tier} pool is empty"
            assert isinstance(body.get("timeout_seconds"), int), (
                f"{tier} has no timeout_seconds"
            )

    def test_it_is_resolvable_as_package_data(self):
        """The whole point is that it travels in the wheel. `registry.yaml`
        already proves hatch ships non-Python files under the package, and
        this is its neighbour — but resolve it the way runtime code will,
        rather than by repo path, so an installed-layout break shows up."""
        from importlib.resources import files

        resource = files("llm_council").joinpath("models/default_pools.yaml")
        assert resource.is_file()
        assert yaml.safe_load(resource.read_text())["pools"]

    def test_the_repo_config_does_not_redeclare_pools(self):
        """`llm_council.yaml` overriding the pools is what let the repo run
        something different from what it shipped — and made the divergence
        invisible, because the repo's own tests read the override. The repo
        now dogfoods the shipped defaults."""
        tiers = yaml.safe_load(REPO_CONFIG.read_text())["council"]["tiers"]
        assert "pools" not in tiers, (
            "llm_council.yaml re-declares tiers.pools. That is a second copy: "
            "it shadows the packaged defaults for this repo only, so the repo "
            "stops exercising what users get. Edit "
            "src/llm_council/models/default_pools.yaml instead."
        )


class TestTheModulesReadItRatherThanRepeatingIt:
    def test_tier_contract_pools_match_the_packaged_file(self, packaged):
        from llm_council.tier_contract import _DEFAULT_TIER_MODEL_POOLS

        assert _DEFAULT_TIER_MODEL_POOLS == {
            tier: body["models"] for tier, body in packaged.items()
        }

    def test_the_public_alias_is_the_same_object(self):
        """`is`, not `==`. The name claims identity, and equality would still
        pass if the alias became an independent copy that could drift — which
        is the whole subject of this file."""
        from llm_council.tier_contract import (
            _DEFAULT_TIER_MODEL_POOLS,
            TIER_MODEL_POOLS,
        )

        assert TIER_MODEL_POOLS is _DEFAULT_TIER_MODEL_POOLS

    def test_unified_config_fills_pools_from_the_packaged_file(self, packaged):
        from llm_council.unified_config import TierConfig

        resolved = TierConfig().pools
        assert set(resolved) == set(packaged)
        for tier, body in packaged.items():
            assert resolved[tier].models == body["models"], f"{tier} pool differs"
            assert resolved[tier].timeout_seconds == body["timeout_seconds"]

    def test_peer_review_settings_survive_the_move(self, packaged):
        """`quick` carried `peer_review="lightweight"` in the Python literal.
        A YAML round-trip that silently dropped it would downgrade nothing
        visibly and cost real money on every quick consult."""
        from llm_council.unified_config import TierConfig

        assert packaged["quick"].get("peer_review") == "lightweight", (
            "the packaged quick pool must declare peer_review: lightweight — "
            "it was in the Python literal this file replaced"
        )
        assert TierConfig().pools["quick"].peer_review == "lightweight", (
            "quick resolved to standard peer review; the YAML key is not "
            "reaching TierPoolConfig"
        )

    def test_council_models_default_matches_the_default_tier(self, packaged):
        """`CouncilConfig.models` was its own fourth copy, still naming a
        preview model. `council_health_check` compares the two and warned on
        every clean install — a drift detector crying wolf by default is a
        drift detector that gets ignored."""
        from llm_council.unified_config import CouncilConfig, TierConfig

        default_tier = TierConfig().default
        assert CouncilConfig().models == packaged[default_tier]["models"]


class TestALiteralCannotComeBack:
    """Equality checks detect drift between copies that already exist. This
    detects a NEW copy — the actual failure mode, since #685 added no copy,
    it just missed two."""

    @pytest.mark.parametrize(
        "source,target",
        [
            (TIER_CONTRACT_SRC, "_DEFAULT_TIER_MODEL_POOLS"),
            (UNIFIED_CONFIG_SRC, "ensure_default_pools"),
            # The FIELD, not the whole class: `chairman` and `normalizer_model`
            # are single-model settings with no pool to drift from, and
            # forbidding those would be a rule about model ids rather than
            # about duplicated pools.
            (UNIFIED_CONFIG_SRC, "CouncilConfig.models"),
        ],
    )
    def test_no_model_ids_are_hardcoded_in_the_pool_definitions(self, source, target):
        tree = ast.parse(source.read_text())
        node = _find_definition(tree, target)
        assert node is not None, f"{target} not found in {source.name}"
        literals = sorted(
            {
                n.value
                for n in ast.walk(node)
                if isinstance(n, ast.Constant)
                and isinstance(n.value, str)
                and MODEL_ID.match(n.value)
            }
        )
        assert not literals, (
            f"{source.name}:{target} hardcodes model id(s) {literals}. The pools "
            "have one definition — src/llm_council/models/default_pools.yaml — "
            "and #690 is what happens when a second one drifts."
        )


class TestTheTierNamesHaveOneDefinitionToo:
    def test_unified_config_validates_against_the_shared_names(self):
        """`TierConfig.validate_tier_name` used to restate the tier names.
        A second list of tier names drifts exactly the way the second list of
        models did — one axis up, and it is what round 2 of the gate flagged
        as unenforced at runtime."""
        import inspect

        from llm_council.default_pools import TIER_NAMES
        from llm_council.unified_config import TierConfig

        source = inspect.getsource(TierConfig.validate_tier_name)
        assert "TIER_NAMES" in source, "validate_tier_name must use the shared set"
        for name in TIER_NAMES:
            assert TierConfig(default=name).default == name
        with pytest.raises(Exception):
            TierConfig(default="not-a-tier")

    def test_the_packaged_file_declares_exactly_those_tiers(self, packaged):
        from llm_council.default_pools import TIER_NAMES

        assert set(packaged) == set(TIER_NAMES) == EXPECTED_TIERS


class TestTheLoaderRejectsBadData:
    """A broken packaged file must raise, not degrade.

    Pool membership decides who deliberates and what it costs, so a partial
    or corrupted pool is worse than a loud stop. The council gate found the
    first case below on this very module: `models: gpt-4` (a scalar, not a
    list) passed the original check, because a `str` is an iterable of
    one-character `str`s — `all(isinstance(m, str) for m in "gpt-4")` is True
    — and then expanded to `['g','p','t','-','4']`. A silent pool corruption
    in the module written to make silent pool corruption impossible.
    """

    @pytest.mark.parametrize(
        "label,content",
        [
            ("scalar models", "pools:\n  quick:\n    models: gpt-4\n    timeout_seconds: 30\n"),
            ("non-list models", "pools:\n  quick:\n    models: {a: b}\n    timeout_seconds: 30\n"),
            ("empty models", "pools:\n  quick:\n    models: []\n    timeout_seconds: 30\n"),
            ("non-string entry", "pools:\n  quick:\n    models: [1]\n    timeout_seconds: 30\n"),
            ("blank entry", 'pools:\n  quick:\n    models: ["  "]\n    timeout_seconds: 30\n'),
            ("duplicate entry", "pools:\n  quick:\n    models: [a/b, a/b]\n    timeout_seconds: 30\n"),
            ("missing timeout", "pools:\n  quick:\n    models: [a/b]\n"),
            ("zero timeout", "pools:\n  quick:\n    models: [a/b]\n    timeout_seconds: 0\n"),
            ("bool timeout", "pools:\n  quick:\n    models: [a/b]\n    timeout_seconds: true\n"),
            ("tier is not a mapping", "pools:\n  quick: nonsense\n"),
            ("no pools key", "something_else: 1\n"),
            ("empty pools", "pools: {}\n"),
            (
                "a tier is missing",
                "pools:\n  quick:\n    models: [a/b]\n    timeout_seconds: 30\n",
            ),
            (
                "an unknown tier",
                (
                    "pools:\n"
                    "  quick: {models: [a/b], timeout_seconds: 30}\n"
                    "  balanced: {models: [a/b], timeout_seconds: 90}\n"
                    "  high: {models: [a/b], timeout_seconds: 180}\n"
                    "  reasoning: {models: [a/b], timeout_seconds: 600}\n"
                    "  frontier: {models: [a/b], timeout_seconds: 600}\n"
                    "  turbo: {models: [a/b], timeout_seconds: 30}\n"
                ),
            ),
            ("root is a list", "- a\n- b\n"),
            ("root is a scalar", "just a string\n"),
            ("empty file", ""),
        ],
    )
    def test_malformed_data_raises_rather_than_degrading(self, label, content, tmp_path):
        from llm_council import default_pools as dp

        bad = tmp_path / "default_pools.yaml"
        bad.write_text(content, encoding="utf-8")
        with _pointed_at(dp, bad):
            with pytest.raises(dp.DefaultPoolsError):
                dp._load()

    def test_an_unreadable_file_raises_the_documented_error(self, tmp_path):
        """A directory where the file should be, a permissions problem or a
        non-UTF-8 byte all reach callers as DefaultPoolsError. Callers are
        told to catch that for "packaged pools unusable"; an error type that
        escapes the contract makes the promise false."""
        from llm_council import default_pools as dp

        a_directory = tmp_path / "default_pools.yaml"
        a_directory.mkdir()
        with _pointed_at(dp, a_directory):
            with pytest.raises(dp.DefaultPoolsError):
                dp._load()

        not_utf8 = tmp_path / "latin1.yaml"
        not_utf8.write_bytes(b"pools:\n  quick:\n    models: [\xff\xfe]\n")
        with _pointed_at(dp, not_utf8):
            with pytest.raises(dp.DefaultPoolsError):
                dp._load()

    def test_a_missing_file_raises(self, tmp_path):
        from llm_council import default_pools as dp

        with _pointed_at(dp, tmp_path / "absent.yaml"):
            with pytest.raises(dp.DefaultPoolsError):
                dp._load()

    def test_one_callers_mutation_does_not_reach_the_next(self):
        """Both accessors hand out copies. `default_pools()` deep-copies and
        `default_pool_models()` rebuilds each list; without that, a single
        `.append` by any caller would rewrite the defaults process-wide."""
        from llm_council.default_pools import default_pool_models, default_pools

        default_pools()["quick"]["models"].append("vendor/injected")
        default_pool_models()["quick"].append("vendor/injected-too")

        assert "vendor/injected" not in default_pools()["quick"]["models"]
        assert "vendor/injected-too" not in default_pool_models()["quick"]


class TestTheAggregatorIsNotADeadWeight:
    def test_each_tier_aggregator_fits_that_tier_budget(self, packaged):
        """`TIER_AGGREGATORS["quick"]` was `gpt-5.6-luna`, commented
        "Speed-matched", measuring 35.3s against quick's 30s budget — the same
        defect as the pool entry, one line further down the file, and missed
        by the pool review because it is a different dict."""
        from test_tier_pool_hygiene import MEASURED_LATENCY_S

        from llm_council.tier_contract import TIER_AGGREGATORS

        violations = []
        for tier, model in TIER_AGGREGATORS.items():
            measured = MEASURED_LATENCY_S.get(model)
            budget = packaged[tier]["timeout_seconds"]
            if measured is not None and measured > budget:
                violations.append(
                    f"{tier}: aggregator {model} measures {measured}s > {budget}s"
                )
        assert not violations, "\n  ".join(violations)

    def test_every_aggregator_is_a_registered_model(self, packaged):
        from test_tier_pool_hygiene import REGISTRY

        from llm_council.tier_contract import TIER_AGGREGATORS

        registered = {
            m["id"] for m in yaml.safe_load(REGISTRY.read_text())["models"]
        }
        missing = sorted(set(TIER_AGGREGATORS.values()) - registered)
        assert not missing, f"aggregators with no registry entry: {missing}"


@contextlib.contextmanager
def _pointed_at(module, path):
    """Aim the loader at `path`, clearing its cache on both sides.

    `_load` is `lru_cache`d for the process lifetime, so a swap without a
    clear would either read the previous file or poison every later test with
    the temporary one.
    """
    original = module.DEFAULT_POOLS_PATH
    module.DEFAULT_POOLS_PATH = path
    module._load.cache_clear()
    try:
        yield
    finally:
        module.DEFAULT_POOLS_PATH = original
        module._load.cache_clear()


def _find_definition(tree, name):
    """The assignment to, or the def/class of, `name` at any depth.

    A dotted `Class.field` descends into that class first, so a field can be
    pinned without dragging in its siblings.
    """
    if "." in name:
        outer, inner = name.split(".", 1)
        scope = _find_definition(tree, outer)
        return _find_definition(scope, inner) if scope is not None else None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                return node
        elif isinstance(node, ast.Assign):
            if any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets
            ):
                return node
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                return node
    return None
