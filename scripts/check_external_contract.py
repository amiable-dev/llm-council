#!/usr/bin/env python3
"""Diff council's external-spend allowlist against the published contract (#707).

    uvx --from "stdtel==0.5.0" stdtel-conform --print-contract \\
        | python scripts/check_external_contract.py

This DETECTS drift; it never generates anything. `EXTERNAL_ATTRIBUTES` stays a
hand-maintained constant, and `tests/test_issue695_external_spend.py` holds a
second longhand copy that is the actual gate. A constant generated from this
output at build time would let a rename flow straight through, which is the
failure both sides keep longhand copies to prevent.

The published attribute list includes the `std.scope.*` keys. stdtel sets
those on receipt and an emitter must not send them, so they are excluded before
comparing rather than being reported as missing.

Exit 0 when council matches the contract, 1 on drift, 2 on unreadable input.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

sys.path.insert(0, "src")

from llm_council.observability import external_spend as ext  # noqa: E402

SCOPE_PREFIX = "std.scope."
RAISE_ON = "https://github.com/amiable-dev/llm-council/issues/707"


def contract_drift(contract: Dict[str, Any]) -> List[str]:
    """Every way council differs from ``contract``; empty when they agree."""
    problems: List[str] = []

    version = contract.get("contract_version")
    if version != ext.CONTRACT_VERSION:
        problems.append(
            f"contract_version is {version!r}; council implements "
            f"{ext.CONTRACT_VERSION}. Read the announcement on #707, adopt the "
            f"change, then bump CONTRACT_VERSION and the stdtel pin together."
        )

    published = {a for a in contract.get("attributes", []) if not a.startswith(SCOPE_PREFIX)}
    extra = ext.EXTERNAL_ATTRIBUTES - published
    missing = published - ext.EXTERNAL_ATTRIBUTES
    if extra:
        problems.append(
            f"council sends {sorted(extra)}, which the contract does not carry. "
            f"These are dropped silently downstream."
        )
    if missing:
        problems.append(
            f"the contract carries {sorted(missing)}, which council does not "
            f"send. A rename leaves the new column null."
        )
    if ext.EXTERNAL_ATTRIBUTES & {
        a for a in contract.get("attributes", []) if a.startswith(SCOPE_PREFIX)
    }:
        problems.append("council sends std.scope.* keys, which stdtel sets on receipt.")

    sources = set(contract.get("cost_sources", []))
    if sources != ext.CONTRACT_COST_SOURCES:
        problems.append(
            f"cost_sources are {sorted(sources)}; council maps onto "
            f"{sorted(ext.CONTRACT_COST_SOURCES)}."
        )

    for key, ours in (
        ("span_name", ext.SPAN_NAME),
        ("kind", ext.ARTEFACT_KIND),
        ("artefact_source", ext.ARTEFACT_SOURCE),
    ):
        if contract.get(key) != ours:
            problems.append(f"{key} is {contract.get(key)!r}; council sends {ours!r}.")
    return problems


def main() -> int:
    try:
        contract = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"could not read the contract from stdin: {exc}", file=sys.stderr)
        return 2
    problems = contract_drift(contract)
    for problem in problems:
        print(f"DRIFT: {problem}", file=sys.stderr)
    if problems:
        print(f"Raise it on {RAISE_ON} before changing the allowlist.", file=sys.stderr)
        return 1
    print(
        f"external contract v{ext.CONTRACT_VERSION}: "
        f"{len(ext.EXTERNAL_ATTRIBUTES)} attributes match"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
