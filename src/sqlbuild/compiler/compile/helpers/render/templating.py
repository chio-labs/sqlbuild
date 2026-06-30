"""Template expansion helpers for compile input resolution."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlbuild.compiler.compile.constants import TEMPLATE_PATTERN
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main.project_var_values import render_project_var_text
from sqlbuild.compiler.compile.types import TemplateNamespace


@dataclass(frozen=True)
class _TemplateToken:
    kind: str
    value: str
    position: int


@dataclass(frozen=True)
class _TemplateStringExpr:
    value: str


@dataclass(frozen=True)
class _TemplateReferenceExpr:
    value: str


@dataclass(frozen=True)
class _TemplateFunctionExpr:
    name: str
    arguments: tuple[object, ...]


_TEMPLATE_END_TOKEN: str = "end"
_TEMPLATE_WORD_TOKEN: str = "word"
_TEMPLATE_STRING_TOKEN: str = "string"
_TEMPLATE_SYMBOL_TOKEN: str = "symbol"
_TEMPLATE_SYMBOLS: frozenset[str] = frozenset({"(", ")", ","})
_TEMPLATE_QUOTE_NAMES: dict[str, str] = {"'": "single", '"': "double"}


def expand_effective_vars(raw_values: dict[str, object]) -> dict[str, object]:
    """Resolve merged effective vars with recursive `${name}` expansion."""

    resolved_values: dict[str, object] = {}
    resolving_keys: list[str] = []

    def resolve_key(key: str) -> object:
        if key not in raw_values:
            raise CompileInputError(f"effective vars references unknown variable '{key}'")
        if key in resolved_values:
            return resolved_values[key]
        if key in resolving_keys:
            cycle: str = " -> ".join((*resolving_keys, key))
            raise CompileInputError(f"effective vars contain a cyclic reference: {cycle}")

        resolving_keys.append(key)
        raw_value: object = raw_values[key]
        if not isinstance(raw_value, str):
            resolving_keys.pop()
            resolved_values[key] = raw_value
            return raw_value
        resolved_value: str = expand_template_string(
            raw_value,
            variables=raw_values,
            resolve_variable=resolve_key,
            context_values={},
            context_label="effective vars",
            allow_context=False,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
        resolving_keys.pop()
        resolved_values[key] = resolved_value
        return resolved_value

    key: str
    for key in raw_values:
        resolve_key(key)
    return resolved_values


def expand_template_data(
    value: object,
    *,
    variables: dict[str, object],
    context_values: dict[str, str | None],
    context_label: str,
    allow_context: bool,
    preserve_context_tokens: bool,
    preserve_unknown_context: bool,
) -> object:
    """Recursively expand template strings inside supported Python container values."""

    if isinstance(value, str):
        resolver: _TemplateResolver = _TemplateResolver(
            variables=variables,
            resolve_variable=lambda name: _lookup_variable(
                name=name,
                variables=variables,
                context_label=context_label,
            ),
            context_values=context_values,
            context_label=context_label,
            allow_context=allow_context,
            preserve_context_tokens=preserve_context_tokens,
            preserve_unknown_context=preserve_unknown_context,
        )
        full_match: re.Match[str] | None = TEMPLATE_PATTERN.fullmatch(value)
        if full_match is not None:
            return resolver.evaluate_token(full_match.group(1))
        return resolver.expand_string(value)
    if isinstance(value, dict):
        return {
            key: expand_template_data(
                item_value,
                variables=variables,
                context_values=context_values,
                context_label=context_label,
                allow_context=allow_context,
                preserve_context_tokens=preserve_context_tokens,
                preserve_unknown_context=preserve_unknown_context,
            )
            for key, item_value in value.items()
        }
    if isinstance(value, list):
        return [
            expand_template_data(
                item,
                variables=variables,
                context_values=context_values,
                context_label=context_label,
                allow_context=allow_context,
                preserve_context_tokens=preserve_context_tokens,
                preserve_unknown_context=preserve_unknown_context,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            expand_template_data(
                item,
                variables=variables,
                context_values=context_values,
                context_label=context_label,
                allow_context=allow_context,
                preserve_context_tokens=preserve_context_tokens,
                preserve_unknown_context=preserve_unknown_context,
            )
            for item in value
        )
    return value


def expand_template_string(
    value: str,
    *,
    variables: dict[str, object],
    resolve_variable: Callable[[str], object],
    context_values: dict[str, str | None],
    context_label: str,
    allow_context: bool,
    preserve_context_tokens: bool,
    preserve_unknown_context: bool,
) -> str:
    """Expand `${...}` templates within a single string value."""

    resolver: _TemplateResolver = _TemplateResolver(
        variables=variables,
        resolve_variable=resolve_variable,
        context_values=context_values,
        context_label=context_label,
        allow_context=allow_context,
        preserve_context_tokens=preserve_context_tokens,
        preserve_unknown_context=preserve_unknown_context,
    )
    return resolver.expand_string(value)


class _TemplateResolver:
    def __init__(
        self,
        *,
        variables: dict[str, object],
        resolve_variable: Callable[[str], object],
        context_values: dict[str, str | None],
        context_label: str,
        allow_context: bool,
        preserve_context_tokens: bool,
        preserve_unknown_context: bool,
    ) -> None:
        self.variables = variables
        self.resolve_variable = resolve_variable
        self.context_values = context_values
        self.context_label = context_label
        self.allow_context = allow_context
        self.preserve_context_tokens = preserve_context_tokens
        self.preserve_unknown_context = preserve_unknown_context

    def expand_string(self, value: str) -> str:
        def replace_match(match: re.Match[str]) -> str:
            token: str = match.group(1)
            return _stringify_template_value(
                value=self.evaluate_token(token),
                label=f"{self.context_label} variable '{token}'",
            )

        return TEMPLATE_PATTERN.sub(replace_match, value)

    def evaluate_token(self, token: str) -> object:
        parser: _TemplateExpressionParser = _TemplateExpressionParser(token)
        expression: object = parser.parse()
        return self._evaluate_expression(expression)

    def _evaluate_expression(self, expression: object) -> object:
        if isinstance(expression, _TemplateStringExpr):
            return expression.value
        if isinstance(expression, _TemplateReferenceExpr):
            return self._evaluate_reference(expression.value)
        if isinstance(expression, _TemplateFunctionExpr):
            return self._evaluate_function(expression)
        raise CompileInputError(f"{self.context_label} contains unsupported template expression")

    def _evaluate_reference(self, value: str) -> object:
        if value == "true":
            return True
        if value == "false":
            return False
        if value == "null":
            return None
        if ":" not in value:
            return self.resolve_variable(value)

        namespace: str
        name: str
        namespace, name = value.split(":", 1)
        if namespace == TemplateNamespace.ENV:
            return _lookup_environment_variable(name=name, context_label=self.context_label)
        if namespace == TemplateNamespace.CTX:
            if not self.allow_context:
                if self.preserve_context_tokens:
                    return f"${{{value}}}"
                raise CompileInputError(f"{self.context_label} does not allow CTX templates")
            return _lookup_context_value(
                name=name,
                context_values=self.context_values,
                context_label=self.context_label,
                preserve_unknown_context=self.preserve_unknown_context,
            )
        raise CompileInputError(
            f"{self.context_label} references unsupported template namespace '{namespace}'"
        )

    def _evaluate_function(self, expression: _TemplateFunctionExpr) -> object:
        function_name: str = expression.name
        if function_name == "if":
            if len(expression.arguments) != 3:
                raise CompileInputError(f"{self.context_label} if(...) expects 3 arguments")
            condition_value: object = self._evaluate_expression(expression.arguments[0])
            if _is_truthy_template_value(condition_value):
                return self._evaluate_expression(expression.arguments[1])
            return self._evaluate_expression(expression.arguments[2])
        if function_name == "eq":
            if len(expression.arguments) != 2:
                raise CompileInputError(f"{self.context_label} eq(...) expects 2 arguments")
            left: object = self._evaluate_expression(expression.arguments[0])
            right: object = self._evaluate_expression(expression.arguments[1])
            return _normalize_template_comparison_value(
                left
            ) == _normalize_template_comparison_value(right)
        if function_name == "ne":
            if len(expression.arguments) != 2:
                raise CompileInputError(f"{self.context_label} ne(...) expects 2 arguments")
            left = self._evaluate_expression(expression.arguments[0])
            right = self._evaluate_expression(expression.arguments[1])
            return _normalize_template_comparison_value(
                left
            ) != _normalize_template_comparison_value(right)
        if function_name == "coalesce":
            if not expression.arguments:
                raise CompileInputError(
                    f"{self.context_label} coalesce(...) expects at least 1 argument"
                )
            argument: object
            for argument in expression.arguments:
                value: object | None = self._evaluate_optional_expression(argument)
                if _is_truthy_template_value(value):
                    return value
            return self._evaluate_expression(expression.arguments[-1])
        raise CompileInputError(
            f"{self.context_label} references unsupported template function '{function_name}'"
        )

    def _evaluate_optional_expression(self, expression: object) -> object | None:
        try:
            return self._evaluate_expression(expression)
        except CompileInputError as error:
            if _is_missing_template_value_error(str(error)):
                return None
            raise


class _TemplateExpressionParser:
    def __init__(self, token: str) -> None:
        self._tokens: list[_TemplateToken] = _tokenize_template_expression(token)
        self._index: int = 0

    def parse(self) -> object:
        expression: object = self._parse_expression()
        self._expect_end()
        return expression

    def _parse_expression(self) -> object:
        token: _TemplateToken = self._peek()
        if token.kind == _TEMPLATE_STRING_TOKEN:
            self._advance()
            return _TemplateStringExpr(token.value)
        if token.kind == _TEMPLATE_WORD_TOKEN:
            self._advance()
            if self._match_symbol("("):
                return self._parse_function_call(token.value)
            return _TemplateReferenceExpr(token.value)
        raise CompileInputError(
            "template expression contains unexpected token "
            f"'{token.value}' at position {token.position}"
        )

    def _parse_function_call(self, name: str) -> _TemplateFunctionExpr:
        arguments: list[object] = []
        while not self._is_at_end_symbol(")"):
            arguments.append(self._parse_expression())
            if not self._match_symbol(","):
                break
        self._consume_symbol(")")
        return _TemplateFunctionExpr(name=name, arguments=tuple(arguments))

    def _is_at_end_symbol(self, symbol: str) -> bool:
        token: _TemplateToken = self._peek()
        return token.kind == _TEMPLATE_SYMBOL_TOKEN and token.value == symbol

    def _match_symbol(self, symbol: str) -> bool:
        token: _TemplateToken = self._peek()
        if token.kind == _TEMPLATE_SYMBOL_TOKEN and token.value == symbol:
            self._advance()
            return True
        return False

    def _consume_symbol(self, symbol: str) -> None:
        if self._match_symbol(symbol):
            return
        token: _TemplateToken = self._peek()
        raise CompileInputError(
            f"template expression expected '{symbol}' at position {token.position}"
        )

    def _expect_end(self) -> None:
        token: _TemplateToken = self._peek()
        if token.kind != _TEMPLATE_END_TOKEN:
            raise CompileInputError(
                "template expression contains unexpected token "
                f"'{token.value}' at position {token.position}"
            )

    def _peek(self) -> _TemplateToken:
        return self._tokens[self._index]

    def _advance(self) -> _TemplateToken:
        token: _TemplateToken = self._tokens[self._index]
        self._index += 1
        return token


def _tokenize_template_expression(value: str) -> list[_TemplateToken]:
    tokens: list[_TemplateToken] = []
    index: int = 0
    while index < len(value):
        character: str = value[index]
        if character.isspace():
            index += 1
            continue
        if character in _TEMPLATE_SYMBOLS:
            tokens.append(
                _TemplateToken(kind=_TEMPLATE_SYMBOL_TOKEN, value=character, position=index)
            )
            index += 1
            continue
        if character in _TEMPLATE_QUOTE_NAMES:
            string_value: str
            next_index: int
            string_value, next_index = _read_template_quoted_string(value=value, start=index)
            tokens.append(
                _TemplateToken(kind=_TEMPLATE_STRING_TOKEN, value=string_value, position=index)
            )
            index = next_index
            continue
        next_index = index
        while next_index < len(value):
            next_character: str = value[next_index]
            if (
                next_character.isspace()
                or next_character in _TEMPLATE_SYMBOLS
                or next_character in _TEMPLATE_QUOTE_NAMES
            ):
                break
            next_index += 1
        word: str = value[index:next_index]
        if not word:
            raise CompileInputError(
                "template expression contains unexpected character "
                f"'{character}' at position {index}"
            )
        tokens.append(_TemplateToken(kind=_TEMPLATE_WORD_TOKEN, value=word, position=index))
        index = next_index
    tokens.append(_TemplateToken(kind=_TEMPLATE_END_TOKEN, value="", position=len(value)))
    return tokens


def _read_template_quoted_string(*, value: str, start: int) -> tuple[str, int]:
    parts: list[str] = []
    quote: str = value[start]
    quote_name: str = _TEMPLATE_QUOTE_NAMES[quote]
    index: int = start + 1
    while index < len(value):
        character: str = value[index]
        if character == "\\":
            if index + 1 >= len(value):
                raise CompileInputError(
                    f"template expression has unterminated escape at position {index}"
                )
            parts.append(value[index + 1])
            index += 2
            continue
        if character == quote:
            return "".join(parts), index + 1
        parts.append(character)
        index += 1
    raise CompileInputError(
        f"template expression has unterminated {quote_name}-quoted string at position {start}"
    )


def _normalize_template_comparison_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _is_truthy_template_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    normalized: str = str(value).strip().lower()
    if normalized in {"", "0", "false"}:
        return False
    return True


def _stringify_template_value(*, value: object, label: str) -> str:
    try:
        return render_project_var_text(value=value, label=label)
    except ValueError as error:
        raise CompileInputError(str(error)) from error


def _is_missing_template_value_error(message: str) -> bool:
    return (
        "references missing ENV variable" in message
        or "references unknown variable" in message
        or "references unknown CTX key" in message
        or "references CTX key" in message
        and "no value is available" in message
    )


def _lookup_variable(*, name: str, variables: dict[str, object], context_label: str) -> object:
    if name not in variables:
        raise CompileInputError(f"{context_label} references unknown variable '{name}'")
    return variables[name]


def _lookup_environment_variable(*, name: str, context_label: str) -> str:
    if name not in os.environ:
        raise CompileInputError(f"{context_label} references missing ENV variable '{name}'")
    return os.environ[name]


def _lookup_context_value(
    *,
    name: str,
    context_values: Mapping[str, str | None],
    context_label: str,
    preserve_unknown_context: bool,
) -> str:
    if name not in context_values:
        if preserve_unknown_context:
            return f"${{{TemplateNamespace.CTX}:{name}}}"
        raise CompileInputError(f"{context_label} references unknown CTX key '{name}'")
    context_value: str | None = context_values.get(name)
    if context_value is None:
        raise CompileInputError(
            f"{context_label} references CTX key '{name}' but no value is available"
        )
    return context_value
