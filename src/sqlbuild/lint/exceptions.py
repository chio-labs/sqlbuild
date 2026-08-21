"""Exceptions raised by the lint and format layer."""

from __future__ import annotations


class LintError(Exception):
    """A lint or format run could not proceed."""
