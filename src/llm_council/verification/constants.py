"""Shared constants for the verification pipeline (split from api.py, #380).

Verbatim move — no logic changes. Back-compat re-exports live in api.py.
"""

from typing import Dict, Set

# Issue #342: legacy default — used only when a caller does not specify a
# tier. Tier-aware paths derive the per-file cap from TIER_MAX_CHARS so a
# single big file (e.g. a 56K ADR at the reasoning tier) is not silently
# amputated by a constant that pre-dates the tier system.
MAX_FILE_CHARS = 15000
# Maximum total characters for all files (legacy default; tier-aware fetch
# scales this to TIER_MAX_CHARS[tier]).
MAX_TOTAL_CHARS = 50000

# =============================================================================
# ADR-034 v2.6: Directory Expansion Constants
# =============================================================================

# Maximum files to include after directory expansion (Issue #309)
MAX_FILES_EXPANSION = 100

# Text file extensions to include (whitelist approach per council decision)
# 80+ extensions covering common source code, config, and documentation files
TEXT_EXTENSIONS: Set[str] = frozenset(
    {
        # Source code
        ".py",
        ".pyi",
        ".pyx",
        ".pxd",  # Python
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",  # JavaScript
        ".ts",
        ".tsx",
        ".mts",
        ".cts",  # TypeScript
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".groovy",  # JVM
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cc",
        ".hh",
        ".cxx",
        ".hxx",  # C/C++
        ".cs",
        ".fs",
        ".fsx",  # .NET
        ".go",  # Go
        ".rs",  # Rust
        ".rb",
        ".rake",
        ".gemspec",  # Ruby
        ".php",
        ".phtml",  # PHP
        ".swift",  # Swift
        ".m",
        ".mm",  # Objective-C
        ".lua",  # Lua
        ".pl",
        ".pm",
        ".t",  # Perl
        ".r",
        ".R",  # R
        ".jl",  # Julia
        ".ex",
        ".exs",  # Elixir
        ".erl",
        ".hrl",  # Erlang
        ".clj",
        ".cljs",
        ".cljc",
        ".edn",  # Clojure
        ".hs",
        ".lhs",  # Haskell
        ".elm",  # Elm
        ".ml",
        ".mli",  # OCaml
        ".nim",  # Nim
        ".v",
        ".sv",
        ".svh",  # Verilog/SystemVerilog
        ".vhd",
        ".vhdl",  # VHDL
        ".asm",
        ".s",  # Assembly
        ".sh",
        ".bash",
        ".zsh",
        ".fish",  # Shell
        ".ps1",
        ".psm1",
        ".psd1",  # PowerShell
        ".bat",
        ".cmd",  # Windows batch
        # Web
        ".html",
        ".htm",
        ".xhtml",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".styl",
        ".vue",
        ".svelte",
        # Data/Config
        ".json",
        ".jsonl",
        ".json5",
        ".yaml",
        ".yml",
        ".toml",
        # #533: .lock is TOML for uv (uv.lock) and plain text for several
        # other ecosystems; deny-listed lockfiles (yarn.lock, poetry.lock,
        # etc.) are excluded separately via GARBAGE_FILENAMES, checked
        # before _is_text_file, so this only affects non-deny-listed ones.
        ".lock",
        ".xml",
        ".xsd",
        ".xsl",
        ".xslt",
        ".svg",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".env.example",
        ".env.sample",
        ".properties",
        ".plist",
        # Documentation
        ".md",
        ".markdown",
        ".mdx",
        ".rst",
        ".txt",
        ".text",
        ".adoc",
        ".asciidoc",
        ".tex",
        ".latex",
        ".org",
        # Build/CI
        ".makefile",
        ".mk",
        ".cmake",
        ".gradle",
        ".dockerfile",
        # GraphQL/API
        ".graphql",
        ".gql",
        ".proto",
        ".thrift",
        ".avsc",  # Avro schema
        # SQL
        ".sql",
        # Misc
        ".vim",
        ".vimrc",
        ".gitignore",
        ".gitattributes",
        ".gitmodules",
        ".editorconfig",
        ".eslintrc",
        ".prettierrc",
        ".stylelintrc",
        ".babelrc",
        ".npmrc",
        ".yarnrc",
        ".dockerignore",
    }
)

# Garbage filenames to exclude (lock files, generated files)
GARBAGE_FILENAMES: Set[str] = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Pipfile.lock",
        "composer.lock",
        "Gemfile.lock",
        "Cargo.lock",
        "go.sum",
        "flake.lock",
        "bun.lockb",
        ".DS_Store",
        "Thumbs.db",
        "desktop.ini",
        "__pycache__",
        "node_modules",
        ".git",
    }
)

# =============================================================================
# End ADR-034 v2.6 Constants
# =============================================================================


# =============================================================================
# ADR-040: Timeout Guardrail Constants
# =============================================================================

# Multiplier for global deadline: tier_contract.deadline_ms * MULTIPLIER.
# Raised 1.5 -> 2.0: at 1.5 a slow day on the `balanced` tier (stage1 ~62s +
# stage2 ~73s) consumed the entire 135s deadline before stage 3 (the chairman
# verdict) even started, so the gate timed out with no verdict. 2.0 gives
# balanced 180s and high 360s so synthesis has room to run; the timeout path
# additionally salvages an advisory signal from completed stages (see below).
VERIFICATION_TIMEOUT_MULTIPLIER = 2.0

# Per-tier maximum input characters (prompt size guardrails)
TIER_MAX_CHARS: Dict[str, int] = {
    "quick": 15000,
    "balanced": 30000,
    "high": 50000,
    "reasoning": 50000,
}

# =============================================================================
# End ADR-040 Constants
# =============================================================================

# =============================================================================
# ADR-042: Evidence Injection Constants
# =============================================================================

# Per-tier ratio of TIER_MAX_CHARS reserved for pre-computed evidence.
# Evidence is carved out BEFORE file content is sized.
MAX_EVIDENCE_CHARS_RATIO: Dict[str, float] = {
    "quick": 0.10,  # 15K * 0.10 =  1.5K chars
    "balanced": 0.20,  # 30K * 0.20 =  6.0K chars
    "high": 0.20,  # 50K * 0.20 = 10.0K chars
    "reasoning": 0.20,  # 50K * 0.20 = 10.0K chars
}



# Async timeout for subprocess operations (seconds)
ASYNC_SUBPROCESS_TIMEOUT = 10
