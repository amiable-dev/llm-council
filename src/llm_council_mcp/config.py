"""Configuration for the LLM Council."""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Default Council members - list of OpenRouter model identifiers
DEFAULT_COUNCIL_MODELS = [
    "openai/gpt-5.1",
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
_style_norm_env = os.getenv("LLM_COUNCIL_STYLE_NORMALIZATION")
STYLE_NORMALIZATION = (
    _style_norm_env.lower() in ('true', '1', 'yes') if _style_norm_env else
    _user_config.get("style_normalization", DEFAULT_STYLE_NORMALIZATION)
)

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
