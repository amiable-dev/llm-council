"""Offline Mode Management for LLM Council (ADR-026).

This module provides offline mode detection and management.
When LLM_COUNCIL_OFFLINE=true, the system uses StaticRegistryProvider
exclusively and disables all external metadata/routing calls.

This implements the "Sovereign Orchestrator" philosophy from ADR-026:
the open-source version must function as a complete, independent utility.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Truthy values for offline mode
TRUTHY_VALUES = {"true", "1", "yes", "on"}


def is_offline_mode() -> bool:
    """Check if offline mode is enabled.

    Offline mode is enabled when LLM_COUNCIL_OFFLINE is set to
    a truthy value (true, 1, yes, on).

    Returns:
        True if offline mode is enabled
    """
    value = os.environ.get("LLM_COUNCIL_OFFLINE", "").lower()
    return value in TRUTHY_VALUES


def check_offline_mode_startup() -> None:
    """Log offline mode status on startup.

    Should be called during application initialization to inform
    users about offline mode status.
    """
    if is_offline_mode():
        logger.info(
            "LLM Council running in OFFLINE mode. "
            "Using StaticRegistryProvider with bundled metadata. "
            "Some features may have limited/stale data."
        )
    else:
        logger.debug("LLM Council running in online mode.")


def get_offline_mode_env_var() -> Optional[str]:
    """Get the raw value of the offline mode environment variable.

    Returns:
        The raw environment variable value, or None if not set
    """
    return os.environ.get("LLM_COUNCIL_OFFLINE")
