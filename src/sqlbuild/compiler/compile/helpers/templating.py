"""Template expansion helpers for compile input resolution."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping

from sqlbuild.compiler.compile.constants import TEMPLATE_PATTERN
from sqlbuild.compiler.compile.exceptions import CompileInputError


def expand_effective_vars(raw_values: dict[str, str]) -> dict[str, str]:
    """Resolve merged effective vars with recursive `${name}` expansion."""

    resolved_values: dict[str, str] = {}
    resolving_keys: list[str] = []

    def resolve_key(key: str) -> str:
        if key not in raw_values:
            raise CompileInputError(f"effective vars references unknown variable '{key}'")
        if key in resolved_values:
            return resolved_values[key]
        if key in resolving_keys:
            cycle: str = " -> ".join((*resolving_keys, key))
            raise CompileInputError(f"effective vars contain a cyclic reference: {cycle}")

        resolving_keys.append(key)
        resolved_value: str = expand_template_string(
            raw_values[key],
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
    variables: dict[str, str],
    context_values: dict[str, str | None],
    context_label: str,
    allow_context: bool,
    preserve_context_tokens: bool,
    preserve_unknown_context: bool,
) -> object:
    """Recursively expand template strings inside supported Python container values."""

    if isinstance(value, str):
        return expand_template_string(
            value,
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
    variables: dict[str, str],
    resolve_variable: Callable[[str], str],
    context_values: dict[str, str | None],
    context_label: str,
    allow_context: bool,
    preserve_context_tokens: bool,
    preserve_unknown_context: bool,
) -> str:
    """Expand `${...}` templates within a single string value."""

    def replace_match(match: re.Match[str]) -> str:
        token: str = match.group(1)
        if ":" not in token:
            return resolve_variable(token)

        namespace: str
        name: str
        namespace, name = token.split(":", 1)
        if namespace == "ENV":
            return _lookup_environment_variable(name=name, context_label=context_label)
        if namespace == "CTX":
            if not allow_context:
                if preserve_context_tokens:
                    return match.group(0)
                raise CompileInputError(f"{context_label} does not allow CTX templates")
            return _lookup_context_value(
                name=name,
                context_values=context_values,
                context_label=context_label,
                preserve_unknown_context=preserve_unknown_context,
            )
        raise CompileInputError(
            f"{context_label} references unsupported template namespace '{namespace}'"
        )

    return TEMPLATE_PATTERN.sub(replace_match, value)


def _lookup_variable(*, name: str, variables: dict[str, str], context_label: str) -> str:
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
            return f"${{CTX:{name}}}"
        raise CompileInputError(f"{context_label} references unknown CTX key '{name}'")
    context_value: str | None = context_values.get(name)
    if context_value is None:
        raise CompileInputError(
            f"{context_label} references CTX key '{name}' but no value is available"
        )
    return context_value
