"""Structured errors for the dupscore duplication-risk advisory tool."""

from __future__ import annotations


class DupscoreConfigError(ValueError):
    """Raised when the dupscore TOML configuration is missing or invalid."""


class DupscoreGitError(RuntimeError):
    """Raised when a git query required by dupscore fails."""


class DupscoreUsageError(ValueError):
    """Raised when CLI arguments cannot be interpreted."""
