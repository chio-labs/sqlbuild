"""Exceptions raised by the lint and format layer."""

from __future__ import annotations


class LintError(Exception):
    """A lint or format run could not proceed."""

    code: str = "L001"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class InterpolationRestorationError(LintError):
    """A formatted SQL body no longer contains exactly one of each sentinel."""

    code: str = "L002"


class SqruffOutputError(LintError):
    """The sqruff engine produced output that could not be interpreted."""

    code: str = "L003"


class UnsupportedDialectError(LintError):
    """The configured sqruff dialect is not one the engine recognises."""

    code: str = "L004"


class ProjectCompileError(LintError):
    """The project could not be compiled, so its SQL cannot be linted."""

    code: str = "L005"
