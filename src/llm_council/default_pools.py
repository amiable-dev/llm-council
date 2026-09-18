"""The single source of truth for the default tier model pools (#690).

`models/default_pools.yaml` ships in the wheel. Everything that needs a
default pool reads it through here, so there is one definition rather than
one per module.

## Why this module exists

The pools used to be written out three times: as a Python literal in
:mod:`llm_council.tier_contract`, as another in
:meth:`llm_council.unified_config.TierConfig.ensure_default_pools`, and in the
repo's ``llm_council.yaml`` — which is not packaged. A model refresh (#685)
updated only the unpackaged one, so every published claim about the new pools
was false for anyone installing from PyPI, and the hygiene tests could not see
it because they read the copy that happened to be right.

## Failure posture

A missing or malformed data file raises. Pool membership decides which models
deliberate and what they cost; a silent fallback to an empty or partial pool
would degrade a council invisibly, which is exactly the failure class this
codebase treats as worse than a loud stop. Telemetry soft-fails here;
correctness does not.
"""

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

DEFAULT_POOLS_PATH = Path(__file__).parent / "models" / "default_pools.yaml"

# The canonical tier names. Defined here because this is the lowest module that
# needs them, and imported by `unified_config` rather than restated there — a
# second list of tier names is the same defect as a second list of models, one
# axis up.
TIER_NAMES = frozenset({"quick", "balanced", "high", "reasoning", "frontier"})


class DefaultPoolsError(RuntimeError):
    """The packaged pool definitions are missing or unusable."""


@lru_cache(maxsize=1)
def _load() -> Dict[str, Dict[str, Any]]:
    """Parse and validate the packaged file. Cached for the process lifetime.

    `_load.cache_clear()` is the supported way to force a re-read; tests that
    point :data:`DEFAULT_POOLS_PATH` elsewhere must call it on both sides of
    the swap.
    """
    try:
        raw = yaml.safe_load(DEFAULT_POOLS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - broken install
        raise DefaultPoolsError(
            f"packaged tier pools missing at {DEFAULT_POOLS_PATH}; the install "
            "is incomplete"
        ) from exc
    except yaml.YAMLError as exc:
        raise DefaultPoolsError(f"{DEFAULT_POOLS_PATH} is not valid YAML") from exc
    except (OSError, UnicodeDecodeError) as exc:
        # Unreadable, a directory, wrong permissions, not UTF-8. Callers are
        # told to catch DefaultPoolsError for "packaged pools unusable"; an
        # error type that escapes that contract makes the promise false.
        raise DefaultPoolsError(f"{DEFAULT_POOLS_PATH} could not be read: {exc}") from exc

    if not isinstance(raw, dict):
        raise DefaultPoolsError(
            f"{DEFAULT_POOLS_PATH} must be a YAML mapping, got {type(raw).__name__}"
        )
    pools = raw.get("pools")
    if not isinstance(pools, dict) or not pools:
        raise DefaultPoolsError(f"{DEFAULT_POOLS_PATH} declares no 'pools' mapping")

    # A file that lost a tier would otherwise load fine and produce a partial
    # tier configuration — the silent degradation this module exists to stop.
    # The completeness invariant belonged in the runtime, not only in CI:
    # a wheel does not run the test suite.
    missing = TIER_NAMES - set(pools)
    if missing:
        raise DefaultPoolsError(
            f"{DEFAULT_POOLS_PATH} is missing tier(s) {sorted(missing)}"
        )
    unknown = {t for t in pools if not isinstance(t, str) or t not in TIER_NAMES}
    if unknown:
        raise DefaultPoolsError(
            f"{DEFAULT_POOLS_PATH} declares unknown tier(s) {sorted(map(str, unknown))}"
        )

    for tier, body in pools.items():
        if not isinstance(body, dict):
            raise DefaultPoolsError(
                f"{DEFAULT_POOLS_PATH}: tier {tier!r} must be a mapping"
            )
        models = body.get("models")
        # `isinstance(models, list)` is load-bearing, NOT redundant with the
        # element check below. A str is an iterable of 1-character strs, so a
        # scalar `models: gpt-4` would satisfy `all(isinstance(m, str) ...)`
        # and then expand to ['g','p','t','-','4'] — a silently bogus council.
        # Found by the council gate on this very file, in the module whose
        # stated purpose is to make silent pool corruption impossible.
        if not isinstance(models, list) or not models:
            raise DefaultPoolsError(
                f"{DEFAULT_POOLS_PATH}: tier {tier!r} must declare a non-empty "
                f"list of models, got {models!r}"
            )
        for model in models:
            if not isinstance(model, str) or not model.strip():
                raise DefaultPoolsError(
                    f"{DEFAULT_POOLS_PATH}: tier {tier!r} has a blank or "
                    f"non-string model entry {model!r}"
                )
        if len(set(models)) != len(models):
            raise DefaultPoolsError(
                f"{DEFAULT_POOLS_PATH}: tier {tier!r} repeats a model"
            )

        timeout = body.get("timeout_seconds")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise DefaultPoolsError(
                f"{DEFAULT_POOLS_PATH}: tier {tier!r} needs a positive integer "
                f"timeout_seconds, got {timeout!r}"
            )
    return pools


def default_pools() -> Dict[str, Dict[str, Any]]:
    """Every tier's full default spec — models, timeout_seconds, peer_review.

    Returns a deep copy: callers build mutable config objects from this, and
    a shared cached dict would let one caller's edit reach every other.
    """
    return deepcopy(_load())


def default_pool_models() -> Dict[str, List[str]]:
    """Just the model lists, `{tier: [model_id, ...]}`.

    The `list()` is load-bearing, not cosmetic: without it every caller would
    share the cached list and one `.append` would rewrite the defaults for the
    whole process.
    """
    return {tier: list(body["models"]) for tier, body in _load().items()}
