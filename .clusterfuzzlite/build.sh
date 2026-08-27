#!/bin/bash -eu

# Only the package itself is needed to import the fuzzed module — no
# server/mcp extras, keeps the build minimal.
pip3 install $SRC/llm-council

compile_python_fuzzer $SRC/llm-council/.clusterfuzzlite/fuzz_ranking_parser.py

# Seed corpus (OSS-Fuzz convention: <fuzzer_name>_seed_corpus.zip in $OUT)
# steers the coverage-guided fuzzer toward the parser's real branches
# (refusal detection, fenced/raw JSON, legacy FINAL RANKING: format) instead
# of only discovering them by chance from random bytes.
zip -j "$OUT/fuzz_ranking_parser_seed_corpus.zip" \
    $SRC/llm-council/.clusterfuzzlite/seed_corpus/*
