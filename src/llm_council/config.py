"""Configuration for the LLM Council."""

import os
import sys
import json
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# ADR-013: Secure API Key Handling
# =============================================================================
# Key resolution priority (per Council recommendation):
# 1. Environment variable (explicit override, CI/CD standard)
# 2. System Keychain/Credential Manager (desktop security)
# 3. .env file (via dotenv - already loaded above)
# 4. Config file (least secure, warn user)

# Track which source the key came from (for diagnostics)
_key_source: Optional[str] = None

# Optional keyring import - may not be installed
keyring = None
try:
    import keyring as _keyring_module
    keyring = _keyring_module
except ImportError:
    pass  # keyring not installed - this is fine


def _is_fail_backend() -> bool:
    """Check if keyring has a fail backend (headless/Docker)."""
    if keyring is None:
        return True
    try:
        from keyring.backends import fail
        return isinstance(keyring.get_keyring(), fail.Keyring)
    except Exception:
        return True


def _get_api_key_from_keychain() -> Optional[str]:
    """Attempt to retrieve API key from system keychain (ADR-013)."""
    if keyring is None:
        return None

    try:
        # Check if we have a real backend (not the fail backend)
        if _is_fail_backend():
            return None

        key = keyring.get_password("llm-council", "openrouter_api_key")
        return key
    except Exception:
        # Keychain access failed (headless, permissions, etc.)
        return None

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Default Council members - list of OpenRouter model identifiers
DEFAULT_COUNCIL_MODELS = [
    "openai/gpt-5.2-pro",
    "google/gemini-3-pro-preview",
    "anthropic/claude-opus-4.5",
    "x-ai/grok-4",
]

# Default Chairman model - synthesizes final response
DEFAULT_CHAIRMAN_MODEL = "google/gemini-3-pro-preview"

# Default synthesis mode: "consensus" or "debate"
# - consensus: Chairman synthesizes a single best answer
# - debate: Chairman highlights key disagreements and trade-offs
DEFAULT_SYNTHESIS_MODE = "consensus"

# Whether to exclude self-votes from ranking aggregation
DEFAULT_EXCLUDE_SELF_VOTES = True

# Whether to normalize response styles before peer review (Stage 1.5)
# Options: False (never), True (always), "auto" (when variance detected)
DEFAULT_STYLE_NORMALIZATION = False

# Model to use for style normalization (fast/cheap model recommended)
DEFAULT_NORMALIZER_MODEL = "google/gemini-2.0-flash-001"

# Maximum number of reviewers per response for stratified sampling
# Set to None to have all models review all responses
# Recommended: 3 for councils with > 5 models
DEFAULT_MAX_REVIEWERS = None


def _load_user_config():
    """Load user configuration from config file if it exists."""
    config_dir = Path.home() / ".config" / "llm-council"
    config_file = config_dir / "config.json"
    
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except Exception:
            # If config file is invalid, return empty dict
            return {}
    return {}


def _get_models_from_env():
    """Get models from environment variable if set."""
    models_env = os.getenv("LLM_COUNCIL_MODELS")
    if models_env:
        # Comma-separated list of models
        return [m.strip() for m in models_env.split(",")]
    return None


# Load user configuration
_user_config = _load_user_config()


def _get_api_key() -> Optional[str]:
    """
    Resolve API key with priority (ADR-013, per Council recommendation):
    1. Environment variable (explicit override, CI/CD standard)
    2. System keychain (desktop security)
    3. .env file (via dotenv, already loaded)
    4. Config file (warn if used)

    Returns:
        API key string or None if not found
    """
    global _key_source

    # 1. Environment variable takes priority (CI/CD standard)
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        _key_source = "environment"
        return key

    # 2. Try keychain (if available)
    key = _get_api_key_from_keychain()
    if key:
        _key_source = "keychain"
        return key

    # 3. .env file would have set the env var, so this is config file fallback
    config_key = _user_config.get("openrouter_api_key")
    if config_key:
        _key_source = "config_file"
        # Emit warning to stderr (suppressible via LLM_COUNCIL_SUPPRESS_WARNINGS)
        if not os.getenv("LLM_COUNCIL_SUPPRESS_WARNINGS"):
            print(
                "Warning: API key loaded from config file. This is insecure. "
                "Consider using environment variables or keychain. "
                "Set LLM_COUNCIL_SUPPRESS_WARNINGS=1 to silence.",
                file=sys.stderr
            )
        return config_key

    # No key found
    _key_source = None
    return None


def get_key_source() -> Optional[str]:
    """Return the source where the API key was loaded from (ADR-013).

    Returns:
        "environment", "keychain", "config_file", or None if no key found
    """
    return _key_source


# OpenRouter API key - resolved via ADR-013 priority chain
OPENROUTER_API_KEY = _get_api_key()

# Council models - priority: env var > config file > defaults
COUNCIL_MODELS = (
    _get_models_from_env() or 
    _user_config.get("council_models") or 
    DEFAULT_COUNCIL_MODELS
)

# Chairman model - priority: env var > config file > defaults
CHAIRMAN_MODEL = (
    os.getenv("LLM_COUNCIL_CHAIRMAN") or
    _user_config.get("chairman_model") or
    DEFAULT_CHAIRMAN_MODEL
)

# Synthesis mode - priority: env var > config file > defaults
SYNTHESIS_MODE = (
    os.getenv("LLM_COUNCIL_MODE") or
    _user_config.get("synthesis_mode") or
    DEFAULT_SYNTHESIS_MODE
)

# Exclude self-votes - priority: env var > config file > defaults
_exclude_self_env = os.getenv("LLM_COUNCIL_EXCLUDE_SELF_VOTES")
EXCLUDE_SELF_VOTES = (
    _exclude_self_env.lower() in ('true', '1', 'yes') if _exclude_self_env else
    _user_config.get("exclude_self_votes", DEFAULT_EXCLUDE_SELF_VOTES)
)

# Style normalization - priority: env var > config file > defaults
# Supports: false (never), true (always), auto (adaptive detection)
_style_norm_env = os.getenv("LLM_COUNCIL_STYLE_NORMALIZATION")
if _style_norm_env:
    _style_norm_env_lower = _style_norm_env.lower()
    if _style_norm_env_lower == "auto":
        STYLE_NORMALIZATION = "auto"
    else:
        STYLE_NORMALIZATION = _style_norm_env_lower in ('true', '1', 'yes')
else:
    STYLE_NORMALIZATION = _user_config.get("style_normalization", DEFAULT_STYLE_NORMALIZATION)

# Normalizer model - priority: env var > config file > defaults
NORMALIZER_MODEL = (
    os.getenv("LLM_COUNCIL_NORMALIZER_MODEL") or
    _user_config.get("normalizer_model") or
    DEFAULT_NORMALIZER_MODEL
)

# Max reviewers for stratified sampling - priority: env var > config file > defaults
_max_reviewers_env = os.getenv("LLM_COUNCIL_MAX_REVIEWERS")
MAX_REVIEWERS = (
    int(_max_reviewers_env) if _max_reviewers_env else
    _user_config.get("max_reviewers", DEFAULT_MAX_REVIEWERS)
)

# Response caching - priority: env var > config file > defaults
DEFAULT_CACHE_ENABLED = False
DEFAULT_CACHE_TTL = 0  # seconds, 0 = infinite (no expiry)
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "llm-council"

_cache_env = os.getenv("LLM_COUNCIL_CACHE")
CACHE_ENABLED = (
    _cache_env.lower() in ('true', '1', 'yes') if _cache_env else
    _user_config.get("cache_enabled", DEFAULT_CACHE_ENABLED)
)

_cache_ttl_env = os.getenv("LLM_COUNCIL_CACHE_TTL")
CACHE_TTL = (
    int(_cache_ttl_env) if _cache_ttl_env else
    _user_config.get("cache_ttl", DEFAULT_CACHE_TTL)
)

_cache_dir_env = os.getenv("LLM_COUNCIL_CACHE_DIR")
CACHE_DIR = (
    Path(_cache_dir_env) if _cache_dir_env else
    Path(_user_config.get("cache_dir", DEFAULT_CACHE_DIR))
)

# =============================================================================
# ADR-016: Structured Rubric Scoring Configuration
# =============================================================================
# Multi-dimensional evaluation with accuracy ceiling mechanism.
# When enabled, reviewers score on: accuracy, relevance, completeness,
# conciseness, and clarity instead of a single holistic score.

DEFAULT_RUBRIC_SCORING_ENABLED = False  # Off by default for backwards compatibility
DEFAULT_ACCURACY_CEILING_ENABLED = True  # Use accuracy as ceiling when rubric enabled

# Default rubric weights (post-council review)
DEFAULT_RUBRIC_WEIGHTS = {
    "accuracy": 0.35,
    "relevance": 0.10,
    "completeness": 0.20,
    "conciseness": 0.15,
    "clarity": 0.20,
}

# Rubric scoring enabled - priority: env var > config file > default
_rubric_env = os.getenv("LLM_COUNCIL_RUBRIC_SCORING")
RUBRIC_SCORING_ENABLED = (
    _rubric_env.lower() in ('true', '1', 'yes') if _rubric_env else
    _user_config.get("rubric_scoring", DEFAULT_RUBRIC_SCORING_ENABLED)
)

# Accuracy ceiling enabled - priority: env var > config file > default
_ceiling_env = os.getenv("LLM_COUNCIL_ACCURACY_CEILING")
ACCURACY_CEILING_ENABLED = (
    _ceiling_env.lower() in ('true', '1', 'yes') if _ceiling_env else
    _user_config.get("accuracy_ceiling", DEFAULT_ACCURACY_CEILING_ENABLED)
)

# Rubric weights - priority: env vars > config file > defaults
RUBRIC_WEIGHTS = {
    "accuracy": float(os.getenv("LLM_COUNCIL_WEIGHT_ACCURACY",
                     str(_user_config.get("rubric_weights", {}).get("accuracy", DEFAULT_RUBRIC_WEIGHTS["accuracy"])))),
    "relevance": float(os.getenv("LLM_COUNCIL_WEIGHT_RELEVANCE",
                      str(_user_config.get("rubric_weights", {}).get("relevance", DEFAULT_RUBRIC_WEIGHTS["relevance"])))),
    "completeness": float(os.getenv("LLM_COUNCIL_WEIGHT_COMPLETENESS",
                         str(_user_config.get("rubric_weights", {}).get("completeness", DEFAULT_RUBRIC_WEIGHTS["completeness"])))),
    "conciseness": float(os.getenv("LLM_COUNCIL_WEIGHT_CONCISENESS",
                        str(_user_config.get("rubric_weights", {}).get("conciseness", DEFAULT_RUBRIC_WEIGHTS["conciseness"])))),
    "clarity": float(os.getenv("LLM_COUNCIL_WEIGHT_CLARITY",
                    str(_user_config.get("rubric_weights", {}).get("clarity", DEFAULT_RUBRIC_WEIGHTS["clarity"])))),
}

# Validate rubric weights sum to 1.0
_rubric_weight_sum = sum(RUBRIC_WEIGHTS.values())
if abs(_rubric_weight_sum - 1.0) > 0.01:
    import warnings
    warnings.warn(f"Rubric weights sum to {_rubric_weight_sum}, not 1.0. Results may be unexpected.")


# =============================================================================
# ADR-016: Safety Gate Configuration
# =============================================================================
# Pass/fail safety check before rubric scoring applies.
# Filters harmful content (dangerous instructions, malware, self-harm, PII).
# When enabled, responses failing safety checks are capped at score 0.

DEFAULT_SAFETY_GATE_ENABLED = False  # Off by default for backwards compatibility
DEFAULT_SAFETY_SCORE_CAP = 0.0  # Score cap for failed safety checks

# Safety gate enabled - priority: env var > config file > default
_safety_gate_env = os.getenv("LLM_COUNCIL_SAFETY_GATE")
SAFETY_GATE_ENABLED = (
    _safety_gate_env.lower() in ('true', '1', 'yes') if _safety_gate_env else
    _user_config.get("safety_gate", DEFAULT_SAFETY_GATE_ENABLED)
)

# Safety score cap - priority: env var > config file > default
_safety_cap_env = os.getenv("LLM_COUNCIL_SAFETY_SCORE_CAP")
SAFETY_SCORE_CAP = (
    float(_safety_cap_env) if _safety_cap_env else
    float(_user_config.get("safety_score_cap", DEFAULT_SAFETY_SCORE_CAP))
)


# =============================================================================
# ADR-015: Bias Auditing Configuration
# =============================================================================
# Automatically detect systematic biases in peer review scoring:
# - Length-score correlation (verbosity bias)
# - Position bias (primacy/recency effects)
# - Reviewer calibration (harsh vs generous reviewers)

DEFAULT_BIAS_AUDIT_ENABLED = False  # Off by default for backwards compatibility
DEFAULT_LENGTH_CORRELATION_THRESHOLD = 0.3  # |r| above this = bias detected
DEFAULT_POSITION_VARIANCE_THRESHOLD = 0.5   # Score variance by position

# Bias audit enabled - priority: env var > config file > default
_bias_audit_env = os.getenv("LLM_COUNCIL_BIAS_AUDIT")
BIAS_AUDIT_ENABLED = (
    _bias_audit_env.lower() in ('true', '1', 'yes') if _bias_audit_env else
    _user_config.get("bias_audit", DEFAULT_BIAS_AUDIT_ENABLED)
)

# Length correlation threshold - priority: env var > config file > default
_length_corr_env = os.getenv("LLM_COUNCIL_LENGTH_CORRELATION_THRESHOLD")
LENGTH_CORRELATION_THRESHOLD = (
    float(_length_corr_env) if _length_corr_env else
    float(_user_config.get("length_correlation_threshold", DEFAULT_LENGTH_CORRELATION_THRESHOLD))
)

# Position variance threshold - priority: env var > config file > default
_position_var_env = os.getenv("LLM_COUNCIL_POSITION_VARIANCE_THRESHOLD")
POSITION_VARIANCE_THRESHOLD = (
    float(_position_var_env) if _position_var_env else
    float(_user_config.get("position_variance_threshold", DEFAULT_POSITION_VARIANCE_THRESHOLD))
)


# =============================================================================
# ADR-018: Cross-Session Bias Persistence Configuration
# =============================================================================
# Accumulate bias metrics across sessions for aggregated analysis.
# Stores one record per (session, model, reviewer) combination in JSONL format.
# Only stores one record per (session, model, reviewer) combination.
# JSONL format enables O(N) linear scan aggregation without file I/O hell.
# See: docs/adr/ADR-018-cross-session-bias-aggregation.md

DEFAULT_BIAS_PERSISTENCE_ENABLED = False  # Off for backward compatibility
DEFAULT_BIAS_STORE_PATH = Path.home() / ".llm-council" / "bias_metrics.jsonl"
DEFAULT_BIAS_WINDOW_SESSIONS = 100
DEFAULT_BIAS_WINDOW_DAYS = 30
DEFAULT_MIN_BIAS_SESSIONS = 20
DEFAULT_BIAS_CONSENT_LEVEL = 1  # LOCAL_ONLY

# Bias persistence enabled - priority: env var > config file > default
_bias_persist_env = os.getenv("LLM_COUNCIL_BIAS_PERSISTENCE")
BIAS_PERSISTENCE_ENABLED = (
    _bias_persist_env.lower() in ('true', '1', 'yes') if _bias_persist_env else
    _user_config.get("bias_persistence", DEFAULT_BIAS_PERSISTENCE_ENABLED)
)

# Bias store path - priority: env var > config file > default
_bias_store_env = os.getenv("LLM_COUNCIL_BIAS_STORE")
BIAS_STORE_PATH = (
    Path(_bias_store_env).expanduser() if _bias_store_env else
    Path(_user_config.get("bias_store_path", DEFAULT_BIAS_STORE_PATH)).expanduser()
)

# Rolling window: sessions - priority: env var > config file > default
_bias_window_sessions_env = os.getenv("LLM_COUNCIL_BIAS_WINDOW_SESSIONS")
BIAS_WINDOW_SESSIONS = (
    int(_bias_window_sessions_env) if _bias_window_sessions_env else
    int(_user_config.get("bias_window_sessions", DEFAULT_BIAS_WINDOW_SESSIONS))
)

# Rolling window: days - priority: env var > config file > default
_bias_window_days_env = os.getenv("LLM_COUNCIL_BIAS_WINDOW_DAYS")
BIAS_WINDOW_DAYS = (
    int(_bias_window_days_env) if _bias_window_days_env else
    int(_user_config.get("bias_window_days", DEFAULT_BIAS_WINDOW_DAYS))
)

# Minimum sessions for aggregation - priority: env var > config file > default
_min_bias_sessions_env = os.getenv("LLM_COUNCIL_MIN_BIAS_SESSIONS")
MIN_BIAS_SESSIONS = (
    int(_min_bias_sessions_env) if _min_bias_sessions_env else
    int(_user_config.get("min_bias_sessions", DEFAULT_MIN_BIAS_SESSIONS))
)

# Consent level - priority: env var > config file > default
_bias_consent_env = os.getenv("LLM_COUNCIL_BIAS_CONSENT")
BIAS_CONSENT_LEVEL = (
    int(_bias_consent_env) if _bias_consent_env else
    int(_user_config.get("bias_consent_level", DEFAULT_BIAS_CONSENT_LEVEL))
)

# Hash secret for query hashing (Research consent level only)
BIAS_HASH_SECRET = os.getenv("LLM_COUNCIL_HASH_SECRET", "default-dev-secret-do-not-use-in-prod")


# =============================================================================
# Telemetry Configuration (ADR-001)
# =============================================================================
# Opt-in telemetry for contributing anonymized voting data to the LLM Leaderboard.
# Privacy-first: disabled by default, no query text transmitted at basic levels.
#
# Levels:
#   off      - No telemetry (default)
#   anonymous - Basic voting data (rankings, durations, model counts)
#   debug    - + query_hash for troubleshooting (no actual query content)
#
# Example: export LLM_COUNCIL_TELEMETRY=anonymous

DEFAULT_TELEMETRY_LEVEL = "off"
DEFAULT_TELEMETRY_ENDPOINT = "https://ingest.llmcouncil.ai/v1/events"

# Parse telemetry level from environment
_telemetry_env = os.getenv("LLM_COUNCIL_TELEMETRY", "").lower().strip()
TELEMETRY_LEVEL = _telemetry_env if _telemetry_env in ("off", "anonymous", "debug") else (
    _user_config.get("telemetry_level", DEFAULT_TELEMETRY_LEVEL)
)

# Telemetry enabled if level is not "off"
TELEMETRY_ENABLED = TELEMETRY_LEVEL != "off"

# Telemetry endpoint - can be overridden for self-hosted installations
TELEMETRY_ENDPOINT = (
    os.getenv("LLM_COUNCIL_TELEMETRY_ENDPOINT") or
    _user_config.get("telemetry_endpoint") or
    DEFAULT_TELEMETRY_ENDPOINT
)


# =============================================================================
# ADR-012: Tier-Sovereign Timeout Configuration (Added 2025-12-19)
# =============================================================================
# Configurable timeouts per confidence tier to support reasoning models.
# Each tier has both a total timeout and a per-model timeout.
#
# Tiers:
#   quick     - Fast responses, fewer/simpler models (30s total, 20s per-model)
#   balanced  - Most models respond (90s total, 45s per-model)
#   high      - Full council deliberation (180s total, 90s per-model)
#   reasoning - Deep reasoning models like o1, GPT-5.2-pro (300s total, 150s per-model)
#
# Environment variables:
#   LLM_COUNCIL_TIMEOUT_<TIER>=<seconds>        - Total timeout for tier
#   LLM_COUNCIL_MODEL_TIMEOUT_<TIER>=<seconds>  - Per-model timeout for tier
#   LLM_COUNCIL_TIMEOUT_MULTIPLIER=<float>      - Global multiplier (emergency override)

DEFAULT_TIER_TIMEOUTS = {
    "quick": {"total": 30, "per_model": 20},
    "balanced": {"total": 90, "per_model": 45},
    "high": {"total": 180, "per_model": 90},
    "reasoning": {"total": 600, "per_model": 300},  # 10min total for deep reasoning models
}

# Models that require the reasoning tier
REASONING_MODELS = {
    "openai/o1",
    "openai/o1-preview",
    "openai/o1-mini",
    "openai/gpt-5.2-pro",
}

# Global timeout multiplier (for emergency adjustments)
_timeout_multiplier_env = os.getenv("LLM_COUNCIL_TIMEOUT_MULTIPLIER")
TIMEOUT_MULTIPLIER = float(_timeout_multiplier_env) if _timeout_multiplier_env else 1.0


def get_tier_timeout(tier: str) -> dict:
    """
    Get timeout configuration for a tier, with environment variable overrides.

    Args:
        tier: One of "quick", "balanced", "high", "reasoning"

    Returns:
        dict with "total" and "per_model" timeout values in seconds
    """
    defaults = DEFAULT_TIER_TIMEOUTS.get(tier, DEFAULT_TIER_TIMEOUTS["high"])
    tier_upper = tier.upper()

    # Check for tier-specific env var overrides
    total_env = os.getenv(f"LLM_COUNCIL_TIMEOUT_{tier_upper}")
    per_model_env = os.getenv(f"LLM_COUNCIL_MODEL_TIMEOUT_{tier_upper}")

    total = int(total_env) if total_env else defaults["total"]
    per_model = int(per_model_env) if per_model_env else defaults["per_model"]

    # Apply global multiplier
    return {
        "total": int(total * TIMEOUT_MULTIPLIER),
        "per_model": int(per_model * TIMEOUT_MULTIPLIER),
    }


def infer_tier_from_models(models: list) -> str:
    """
    Auto-select tier based on the slowest model in the council.

    Args:
        models: List of model identifiers

    Returns:
        Recommended tier name
    """
    if any(m in REASONING_MODELS for m in models):
        return "reasoning"
    return "high"
