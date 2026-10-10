"""Expand `${...}` templates natively, returning the value or Python's error with its reads."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.classes.unicode_environment import UnicodeEnvironment
from sqlbuild.compiler.model_config.models import (
    NativeTemplateExpansion,
    NativeTemplateRejection,
    TemplateResolutionFlags,
)


def expand_native_config_templates(
    *,
    value: object,
    variables: dict[str, object],
    context_values: dict[str, str | None],
    flags: TemplateResolutionFlags,
    context_label: str,
) -> NativeTemplateExpansion | NativeTemplateRejection:
    """Return the expanded value, or the error expansion stopped at; both carry their reads."""

    outcome: tuple[object, list[tuple[str, str]]] = _native.expand_config_templates(
        value,
        (variables, UnicodeEnvironment(), context_values),
        (
            flags.allow_context,
            flags.preserve_context_tokens,
            flags.preserve_unknown_context,
            context_label,
        ),
    )
    if isinstance(outcome[0], _native.NativeConfigError):
        return NativeTemplateRejection(error=outcome[0], reads=tuple(outcome[1]))
    return NativeTemplateExpansion(value=outcome[0], reads=tuple(outcome[1]))
