"""Release gate enumerations."""

from __future__ import annotations

from enum import StrEnum


class TokenKind(StrEnum):
    """Lexical class of a workflow expression token."""

    STRING = "string"
    OPERATOR = "operator"
    NAME = "name"


class Operator(StrEnum):
    """Workflow expression operators and punctuation."""

    AND = "&&"
    OR = "||"
    EQUAL = "=="
    NOT_EQUAL = "!="
    NOT = "!"
    OPEN = "("
    CLOSE = ")"
    SEPARATOR = ","


class CheckState(StrEnum):
    """Check run conclusions and commit status states the gate distinguishes."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    NEUTRAL = "neutral"
    PENDING = "pending"
    FAILURE = "failure"
