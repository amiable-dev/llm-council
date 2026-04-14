"""Enforcement tests for Model Centralization (ADR-048).

This module ensures that no hardcoded model identifiers are introduced into the
codebase (src/) or the test suite (tests/), enforcing the use of centralized
constants from llm_council.model_constants.
"""

import os
import re
import pytest
from pathlib import Path

# Common model provider prefixes to look for
FORBIDDEN_PREFIXES = [
    "openai/",
    "anthropic/",
    "google/",
    "qwen/",
    "deepseek/",
    "mistralai/",
    "meta-llama/",
    "cohere/",
    "ollama/",
]

# Files to exclude from enforcement
EXCLUDED_FILES = [
    "model_constants.py",              # The source of truth
    "test_centralization_enforcement.py", # This file itself
    "__init__.py",                     # Package init
    "conftest.py",                     # Pytest config
]

# Patterns that might match the prefix but are legitimate
# (e.g., MIME types, URLs, etc.)
LEGITIMATE_LITERALS = [
    "application/json",
    "text/plain",
    "text/markdown",
    "image/jpeg",
    "image/png",
    "multipart/form-data",
    "https://openrouter.ai/api/v1/",
    "http://localhost:11434/api/",
]

def check_file_for_hardcoded_models(file_path: Path):
    """Scan a file for hardcoded model identifiers."""
    hardcoded_found = []
    
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            # Skip comments and imports
            if line.strip().startswith("#") or line.strip().startswith("import ") or line.strip().startswith("from "):
                continue
                
            for prefix in FORBIDDEN_PREFIXES:
                if prefix in line:
                    # Check if it's a legitimate literal
                    is_legitimate = any(legit in line for legit in LEGITIMATE_LITERALS)
                    if is_legitimate:
                        continue
                        
                    # Extract the potential model ID for better error reporting
                    # Match something/something inside quotes
                    matches = re.findall(f'["\']({prefix}[a-zA-Z0-9._-]+)["\']', line)
                    if matches:
                        hardcoded_found.append((line_num, matches[0], line.strip()))
                        
    return hardcoded_found

@pytest.fixture
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent

def test_no_hardcoded_models_in_src(project_root):
    """Ensure no hardcoded model IDs in src/ directory."""
    src_dir = project_root / "src"
    violations = []
    
    for py_file in src_dir.rglob("*.py"):
        if py_file.name in EXCLUDED_FILES:
            continue
            
        file_violations = check_file_for_hardcoded_models(py_file)
        if file_violations:
            violations.append((py_file.relative_to(project_root), file_violations))
            
    if violations:
        error_msg = "Hardcoded model identifiers found in src/! Use model_constants.py instead.\n\n"
        for file_path, file_violations in violations:
            error_msg += f"File: {file_path}\n"
            for line_num, model_id, context in file_violations:
                error_msg += f"  L{line_num}: {model_id} found in '{context}'\n"
            error_msg += "\n"
        pytest.fail(error_msg)

def test_no_hardcoded_models_in_tests(project_root):
    """Ensure no hardcoded model IDs in tests/ directory."""
    tests_dir = project_root / "tests"
    violations = []
    
    for py_file in tests_dir.rglob("*.py"):
        if py_file.name in EXCLUDED_FILES:
            continue
            
        file_violations = check_file_for_hardcoded_models(py_file)
        if file_violations:
            violations.append((py_file.relative_to(project_root), file_violations))
            
    if violations:
        error_msg = "Hardcoded model identifiers found in tests/! Use model_constants.py instead.\n\n"
        for file_path, file_violations in violations:
            error_msg += f"File: {file_path}\n"
            for line_num, model_id, context in file_violations:
                error_msg += f"  L{line_num}: {model_id} found in '{context}'\n"
            error_msg += "\n"
        pytest.fail(error_msg)
