"""Exceptions raised by the lint and format layer."""

from __future__ import annotations


class LintError(Exception):
    """A lint or format run could not proceed."""


class InterpolationRestorationError(LintError):
    """A formatted SQL body no longer contains exactly one of each sentinel."""


class SqruffOutputError(LintError):
    """The sqruff engine produced output that could not be interpreted."""
