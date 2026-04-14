# src/llm_council/model_constants.py

# Quick Tier Models (Fastest/Cheapest)
OPENAI_QUICK = "openai/gpt-4o-mini"
ANTHROPIC_QUICK = "anthropic/claude-3-haiku"
GOOGLE_QUICK = "google/gemini-2.0-flash-lite-001"
QWEN_QUICK = "qwen/qwen-turbo"
OPENAI_LOW = OPENAI_QUICK

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
OPENAI_ULTRA = "openai/gpt-4-turbo"
GOOGLE_MODEL_LATEST = GOOGLE_HIGH
LLAMA_HIGH = "meta-llama/llama-3.1-405b"

# Reasoning Tier Models
OPENAI_REASONING_PREVIEW = "openai/o1-preview"  # Canonical: specific version
OPENAI_REASONING = OPENAI_REASONING_PREVIEW        # Alias: reasoning-tier pool default
ANTHROPIC_REASONING = "anthropic/claude-3-5-sonnet-20241022"
GOOGLE_REASONING = "google/gemini-3.1-pro-preview"
QWEN_REASONING = "qwen/qwq-32b-preview"
DEEPSEEK_R1 = "deepseek/deepseek-r1"
OPENAI_O3_MINI = "openai/o3-mini"
DEEPSEEK_CHAT = "deepseek/deepseek-chat"
CODESTRAL = "mistralai/codestral-latest"
OPENAI_REASONING_LOW = "openai/o1-mini"


# Utility Models (formatting, normalization, etc.)
UTILITY_TITLE_GENERATOR = "google/gemini-2.0-flash-lite-001"
UTILITY_NORMALIZER_MODEL = "google/gemini-3.1-flash-lite-preview"
HEALTH_CHECK_MODEL = "google/gemini-2.0-flash-001"
OLLAMA_HEALTH_CHECK_MODEL = "ollama/llama3.2"
OLLAMA_ANY = OLLAMA_HEALTH_CHECK_MODEL
OLLAMA_LOCAL = "ollama/local"

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
# Specific versions for test stability
OPENAI_O1 = "openai/o1"           # Canonical: latest o1
OPENAI_O1_PREVIEW = OPENAI_REASONING_PREVIEW  # Alias → "openai/o1-preview"
OPENAI_REASONING_LATEST = OPENAI_O1           # Alias → "openai/o1"
ANTHROPIC_CLAUDE_3_5_SONNET_20241022 = "anthropic/claude-3-5-sonnet-20241022"
ANTHROPIC_CLAUDE_OPUS_REF = "anthropic/claude-opus-4.6"

# Frontier Tier Models (distinct from reasoning — latest/preview cutting-edge models)
FRONTIER_OPENAI = OPENAI_O1              # Latest o1 (not preview)
FRONTIER_ANTHROPIC = ANTHROPIC_HIGH      # claude-3.7-sonnet
FRONTIER_GOOGLE = GOOGLE_HIGH            # gemini-2.5-pro
FRONTIER_DEEPSEEK = DEEPSEEK_R1          # deepseek-r1

# Chairman
CHAIRMAN_MODEL = GOOGLE_REASONING
ENV_VAR_OPENROUTER_API_KEY = "OPENROUTER_API_KEY"  # Legacy attribute for test compatibility

# Reasoning Family Identifiers
REASONING_FAMILY_O1 = "o1"
REASONING_FAMILY_QWQ = "qwq"
REASONING_FAMILY_CLAUDE_3_OPUS = "claude-3-opus"

# Provider Prefixes
PREFIX_OPENAI = "openai/"
PREFIX_ANTHROPIC = "anthropic/"
PREFIX_GOOGLE = "google/"
PREFIX_MISTRAL = "mistralai/"
PREFIX_DEEPSEEK = "deepseek/"
PREFIX_QWEN = "qwen/"
PREFIX_COHERE = "cohere/"
PREFIX_OLLAMA = "ollama/"
