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
OPENAI_REASONING = "openai/o1-preview"
ANTHROPIC_REASONING = "anthropic/claude-3-5-sonnet-20241022"
GOOGLE_REASONING = "google/gemini-3.1-pro-preview"
QWEN_REASONING = "qwen/qwq-32b-preview"

# Utility Models (formatting, normalization, etc.)
UTILITY_TITLE_GENERATOR = "google/gemini-2.0-flash-lite-001"
UTILITY_NORMALIZER_MODEL = "google/gemini-3.1-flash-lite-preview"
HEALTH_CHECK_MODEL = "google/gemini-2.0-flash-001"

# Specialist models (used in triage pools)
WILDCARD_CODE_QWEN = "qwen/qwen-2.5-coder-32b-instruct"
WILDCARD_CODE_MISTRAL = "mistralai/codestral-latest"
WILDCARD_REASONING_O1 = "openai/o1-preview"
WILDCARD_REASONING_QWQ = "qwen/qwq-32b-preview"
WILDCARD_CREATIVE_OPUS = "anthropic/claude-3-opus-20240229"
WILDCARD_CREATIVE_COHERE = "cohere/command-r-plus"

# Additional Frontier Placeholders
ANTHROPIC_OPUS_LATEST = "anthropic/claude-3-opus-20240229"
WILDCARD_FALLBACK_MODEL = "meta-llama/llama-3.1-70b-instruct"

# Chairman
CHAIRMAN_MODEL = GOOGLE_REASONING

# Reasoning Family Identifiers
REASONING_FAMILY_O1 = "o1"
REASONING_FAMILY_QWQ = "qwq"
REASONING_FAMILY_CLAUDE_3_OPUS = "claude-3-opus"
