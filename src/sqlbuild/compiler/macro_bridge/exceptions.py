"""Macro bridge exceptions."""

from __future__ import annotations


class UncacheableValueError(Exception):
    """A value a macro may read has no stable text, so calls that may read it are not stored."""
