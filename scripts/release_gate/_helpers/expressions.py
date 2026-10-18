"""Evaluate the subset of GitHub Actions expressions that workflow job names use."""

from __future__ import annotations

import re
from typing import Any

from scripts.release_gate.constants import (
    EXPRESSION_LITERALS,
    FALSY_VALUES,
    STARTS_WITH_ARGUMENTS,
    STARTS_WITH_FUNCTION,
)
from scripts.release_gate.exceptions import ReleaseGateError
from scripts.release_gate.types import Operator, TokenKind

_TEMPLATE: re.Pattern[str] = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
_TOKEN: re.Pattern[str] = re.compile(
    r"\s*(?:(?P<string>'(?:[^']|'')*')|(?P<operator>&&|\|\||==|!=|!|\(|\)|,)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*))"
)


def evaluate_template(*, template: str, contexts: dict[str, Any]) -> str:
    """Substitute every `${{ }}` expression in `template` with its value under `contexts`."""
    return _TEMPLATE.sub(
        lambda match: _to_string(evaluate(expression=match.group(1), contexts=contexts)),
        template,
    )


def evaluate(*, expression: str, contexts: dict[str, Any]) -> Any:
    """Return the value of one expression under `contexts`."""
    parser: _Parser = _Parser(tokens=_tokenize(expression), contexts=contexts)
    value: Any = parser.parse_or()
    if parser.peek() is not None:
        raise ReleaseGateError(f"Unexpected token {parser.peek()!r} in {expression!r}")
    return value


def _tokenize(expression: str) -> list[tuple[TokenKind, str]]:
    tokens: list[tuple[TokenKind, str]] = []
    position: int = 0
    while expression[position:].strip():
        match: re.Match[str] | None = _TOKEN.match(expression, position)
        if match is None or match.lastgroup is None:
            raise ReleaseGateError(f"Unsupported expression syntax at {expression[position:]!r}")
        tokens.append((TokenKind(match.lastgroup), match.group(match.lastgroup)))
        position = match.end()
    return tokens


class _Parser:
    def __init__(self, *, tokens: list[tuple[TokenKind, str]], contexts: dict[str, Any]) -> None:
        self._tokens: list[tuple[TokenKind, str]] = tokens
        self._contexts: dict[str, Any] = contexts
        self._index: int = 0

    def peek(self) -> str | None:
        return self._tokens[self._index][1] if self._index < len(self._tokens) else None

    def _take(self) -> tuple[TokenKind, str]:
        if self._index >= len(self._tokens):
            raise ReleaseGateError("Unexpected end of expression")
        token: tuple[TokenKind, str] = self._tokens[self._index]
        self._index += 1
        return token

    def _expect(self, operator: Operator) -> None:
        if self._take() != (TokenKind.OPERATOR, operator):
            raise ReleaseGateError(f"Expected {operator.value!r}")

    def parse_or(self) -> Any:
        value: Any = self._parse_and()
        while self.peek() == Operator.OR:
            self._take()
            right: Any = self._parse_and()
            value = value if _truthy(value) else right
        return value

    def _parse_and(self) -> Any:
        value: Any = self._parse_equality()
        while self.peek() == Operator.AND:
            self._take()
            right: Any = self._parse_equality()
            value = right if _truthy(value) else value
        return value

    def _parse_equality(self) -> Any:
        value: Any = self._parse_unary()
        if self.peek() in (Operator.EQUAL, Operator.NOT_EQUAL):
            operator: str = self._take()[1]
            equal: bool = _equal(left=value, right=self._parse_unary())
            return equal if operator == Operator.EQUAL else not equal
        return value

    def _parse_unary(self) -> Any:
        if self.peek() == Operator.NOT:
            self._take()
            return not _truthy(self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> Any:
        kind, text = self._take()
        if (kind, text) == (TokenKind.OPERATOR, Operator.OPEN):
            value: Any = self.parse_or()
            self._expect(Operator.CLOSE)
            return value
        if kind is TokenKind.STRING:
            return text[1:-1].replace("''", "'")
        if kind is not TokenKind.NAME:
            raise ReleaseGateError(f"Unexpected token {text!r}")
        if text in EXPRESSION_LITERALS:
            return EXPRESSION_LITERALS[text]
        if self.peek() == Operator.OPEN:
            return self._call(text)
        return self._lookup(text)

    def _call(self, function: str) -> Any:
        self._expect(Operator.OPEN)
        arguments: list[Any] = [self.parse_or()]
        while self.peek() == Operator.SEPARATOR:
            self._take()
            arguments.append(self.parse_or())
        self._expect(Operator.CLOSE)
        if function.lower() == STARTS_WITH_FUNCTION and len(arguments) == STARTS_WITH_ARGUMENTS:
            return _to_string(arguments[0]).lower().startswith(_to_string(arguments[1]).lower())
        raise ReleaseGateError(f"Unsupported function {function}")

    def _lookup(self, path: str) -> Any:
        value: Any = self._contexts
        for key in path.split("."):
            value = value.get(key) if isinstance(value, dict) else None
        return value


def _truthy(value: Any) -> bool:
    return value not in FALSY_VALUES


def _equal(*, left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return left.lower() == right.lower()
    return left == right


def _to_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
