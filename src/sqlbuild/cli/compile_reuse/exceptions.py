"""Compile reuse storage errors."""

from __future__ import annotations


class CompileReuseEntryError(ValueError):
    """A stored compile is truncated, corrupt, or written in an unknown format."""
