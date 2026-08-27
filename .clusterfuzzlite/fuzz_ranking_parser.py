#!/usr/bin/env python3
"""Atheris coverage-guided fuzz harness for the Stage 2 ranking parser.

Same target as the Hypothesis property tests in
tests/test_fuzz_ranking_parser.py (#657/#658) — parse_ranking_from_text
consumes raw model output unguarded in the Stage 2 results-aggregation loop
(council_stages.py), so it must never raise on arbitrary input.
"""
import sys

import atheris

with atheris.instrument_imports():
    from llm_council.council_rankings import parse_ranking_from_text


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)
    text = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())
    result = parse_ranking_from_text(text)
    assert isinstance(result, dict)
    assert "ranking" in result
    assert "scores" in result


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
