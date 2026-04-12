# Implementation Plan (Architect-Approved): Centralizing LLM Model Names

This revised plan centralizes all hardcoded LLM model identifiers into a leaf-node constants file. It has been updated by a senior architect to adopt a **safe, incremental refactoring strategy** and to reflect the full scope of the work.

---

## 🛑 MANDATORY ARCHITECTURAL RULES

> [!IMPORTANT]
> **Single Source of Truth:** We will create `src/llm_council/model_constants.py` as the single, authoritative source for all model identifiers. All other files will reference this file.

> [!CAUTION]
> **Incremental Changes ONLY:** The refactoring of **38 files** will be broken down into smaller, logically-grouped pull requests. A "big bang" change touching all files at once is not permitted due to the high risk of error.

> [!WARNING]
> **Manual Approval ONLY:** As per our global rules, I will not move to the execution phase or create a `task.md` until you explicitly type **"Approve"** in the chat.

---

## Phase 0: Establish the Foundation

The first step is to create the Single Source of Truth. This change can be merged independently before any refactoring begins.

#### [NEW] `src/llm_council/model_constants.py`
This will be a leaf node with no internal project imports.

```python
# src/llm_council/model_constants.py

# Quick Tier Models (Fastest/Cheapest)
OPENAI_QUICK = "openai/gpt-4o-mini"
ANTHROPIC_QUICK = "anthropic/claude-3-haiku"
GOOGLE_QUICK = "google/gemini-2.0-flash-lite-001"
QWEN_QUICK = "qwen/qwen-turbo"

# Balanced Tier Models
OPENAI_BALANCED = "openai/gpt-4o-mini"
ANTHROPIC_BALANCED = "anthropic/claude-3.5-haiku"
GOOGLE_BALANCED = "google/gemini-2.0-flash-001"
QWEN_BALANCED = "qwen/qwen-turbo"

# High Tier Models
OPENAI_HIGH = "openai/gpt-4o"
ANTHROPIC_HIGH = "anthropic/claude-3.7-sonnet"
GOOGLE_HIGH = "google/gemini-2.5-pro"
QWEN_HIGH = "qwen/qwen-plus"

# Reasoning Tier Models
OPENAI_REASONING = "openai/gpt-5.4"
ANTHROPIC_REASONING = "anthropic/claude-opus-4.6"
GOOGLE_REASONING = "google/gemini-3.1-pro-preview"
QWEN_REASONING = "qwen/qwen-plus"

# Chairman & Utility
CHAIRMAN_MODEL = GOOGLE_REASONING
UTILITY_TITLE_GENERATOR = "google/gemini-2.5-flash"
HEALTH_CHECK_MODEL = "google/gemini-2.0-flash-001"

# Specialist Models
WILDCARD_CODE_QWEN = "qwen/qwen-2.5-coder-32b-instruct"
WILDCARD_CODE_MISTRAL = "mistralai/codestral-latest"
WILDCARD_FALLBACK_MODEL = "meta-llama/llama-3.1-70b-instruct"

# Reasoning Family Identifiers
REASONING_FAMILY_O1 = "o1"
REASONING_FAMILY_QWQ = "qwq"
REASONING_FAMILY_CLAUDE_3_OPUS = "claude-3-opus"
```

---

## Phase 1: Incremental Refactoring

We will refactor **38 files** in small, logical batches. Each batch should be a separate pull request.

### **Batch 1: Core Configuration**
- `src/llm_council/unified_config.py`
- `src/llm_council/tier_contract.py`
- `src/llm_council/mcp_server.py`

### **Batch 2: Triage & Logic**
- `src/llm_council/triage/fast_path.py`
- `src/llm_council/triage/prompt_optimizer.py`
- `src/llm_council/triage/types.py`
- `src/llm_council/triage/not_diamond.py`
- `src/llm_council/triage/__init__.py`

### **Batch 3: Gateway & Connectivity**
- `src/llm_council/gateway/openrouter.py`
- `src/llm_council/gateway/router.py`
- `src/llm_council/gateway/direct.py`
- `src/llm_council/gateway/requesty.py`
- `src/llm_council/gateway/circuit_breaker_registry.py`
- `src/llm_council/gateway/types.py`
- `src/llm_council/gateway/__init__.py`
- `src/llm_council/gateway_adapter.py`
- `src/llm_council/openrouter.py`

### **Batch 4: Metadata Framework**
- `src/llm_council/metadata/discovery.py`
- `src/llm_council/metadata/litellm_adapter.py`
- `src/llm_council/metadata/static_registry.py`
- `src/llm_council/metadata/selection.py`
- `src/llm_council/metadata/scoring.py`
- `src/llm_council/metadata/protocol.py`
- `src/llm_council/metadata/dynamic_provider.py`
- `src/llm_council/metadata/registry.py`
- `src/llm_council/metadata/types.py`
- `src/llm_council/metadata/__init__.py`

### **Batch 5: Audition, Performance & Utilities**
- `src/llm_council/audition/tracker.py`
- `src/llm_council/audition/types.py`
- `src/llm_council/audition/voting.py`
- `src/llm_council/audition/__init__.py`
- `src/llm_council/performance/tracker.py`
- `src/llm_council/performance/types.py`
- `src/llm_council/performance/__init__.py`
- `src/llm_council/reasoning/tracker.py`
- `src/llm_council/reasoning/__init__.py`
- `src/llm_council/utils/formatting.py`
- `src/llm_council/observability/metrics_adapter.py`

---

## Phase 2: Finalize Configuration

This phase occurs **after all code refactoring is complete.**

#### [MODIFY] `llm_council.yaml`
- **Action:** Delete the literal `models:` lists under each tier in `tiers.pools`.
- **Verification:** Ensure the application runs correctly and that tiers successfully fall back to the new Python-defined defaults from `model_constants.py`.

---

## Phase 3: Verification & Quality Gates

These checks must be performed **for each incremental pull request.**

### **Automated Verification**
1. **Lint & Format:** `uv run ruff check . --fix` and `uv run ruff format .`
2. **Type Check:** `uv run mypy src/llm_council --ignore-missing-imports`
3. **Integration Test:** Run full `pytest tests/` repo-wide.

### **Manual Verification**
1. **Health Check:** Run `llm-council health` and verify all listed models match the new pinned constants.
2. **Live Query Test:** Send 2-3 test queries to the council to confirm it processes requests successfully using the new configuration.
3. **Commit Audit:** Verify DCO sign-off (`-s`) on all commits.

---

## Phase 4: The "Self-Reporting Audit" Guardrail

This is the **final step** to prevent future regressions. This should be its own pull request.

#### [NEW] `tests/test_hardcoded_cleanup.py`
- **Mechanism:** A new test that regex-scans all `.py` files in the `src/` directory.
- **Enforcement:** **FAIL THE BUILD** if hardcoded provider strings (e.g., `openai/`, `google/`) are found in any file other than `src/llm_council/model_constants.py`.

---
**[END OF PLAN]**
