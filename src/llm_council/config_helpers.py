"""Configuration helpers with legacy patching support (ADR-032)."""

import sys as _sys
from typing import Optional, Any
from llm_council.unified_config import get_config


def _check_patched_attr(module_name: str, attr_name: str, default: Any = None) -> Any:
    """Check if a module attribute was patched (for test support)."""
    module = _sys.modules.get(module_name)
    if module is not None:
        if attr_name in module.__dict__:
            return module.__dict__[attr_name]
    return default


def _get_council_config():
    """Get council config section."""
    return get_config().council


def _get_council_models(module_name: str = "llm_council.council") -> list:
    patched = _check_patched_attr(module_name, "COUNCIL_MODELS")
    if patched is not None:
        return patched
    return _get_council_config().models


def _get_chairman_model(module_name: str = "llm_council.council") -> str:
    patched = _check_patched_attr(module_name, "CHAIRMAN_MODEL")
    if patched is not None:
        return patched
    return _get_council_config().chairman


def _get_synthesis_mode(module_name: str = "llm_council.council") -> str:
    patched = _check_patched_attr(module_name, "SYNTHESIS_MODE")
    if patched is not None:
        return patched
    return _get_council_config().synthesis_mode


def _get_exclude_self_votes(module_name: str = "llm_council.council") -> bool:
    patched = _check_patched_attr(module_name, "EXCLUDE_SELF_VOTES")
    if patched is not None:
        return patched
    return _get_council_config().exclude_self_votes


def _get_style_normalization(module_name: str = "llm_council.council") -> bool:
    patched = _check_patched_attr(module_name, "STYLE_NORMALIZATION")
    if patched is not None:
        return patched
    return _get_council_config().style_normalization


def _get_normalizer_model(module_name: str = "llm_council.council") -> str:
    patched = _check_patched_attr(module_name, "NORMALIZER_MODEL")
    if patched is not None:
        return patched
    return _get_council_config().normalizer_model


def _get_max_reviewers(module_name: str = "llm_council.council") -> int:
    patched = _check_patched_attr(module_name, "MAX_REVIEWERS")
    if patched is not None:
        return patched
    return _get_council_config().max_reviewers


def _get_adversarial_mode(module_name: str = "llm_council.council") -> bool:
    patched = _check_patched_attr(module_name, "ADVERSARIAL_MODE")
    if patched is not None:
        return patched
    return _get_council_config().adversarial_mode


def _get_adversarial_model(module_name: str = "llm_council.council") -> Optional[str]:
    patched = _check_patched_attr(module_name, "ADVERSARIAL_MODEL")
    if patched is not None:
        return patched
    return _get_council_config().adversarial_model


def _get_cache_enabled(module_name: str = "llm_council.council") -> bool:
    patched = _check_patched_attr(module_name, "CACHE_ENABLED")
    if patched is not None:
        return patched
    return get_config().cache.enabled
