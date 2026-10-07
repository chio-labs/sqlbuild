"""Expand `${...}` templates in model config natively for the preview compiler engine."""

from __future__ import annotations

import os

import sqlbuild._native as _native
from sqlbuild.compiler.model_config.constants import UNSUPPORTED_OUTCOME
from sqlbuild.compiler.model_config.models import (
    NativeTemplateExpansion,
    TemplateResolutionFlags,
)


def expand_native_config_templates(
    *,
    value: object,
    variables: dict[str, object],
    context_values: dict[str, str | None],
    flags: TemplateResolutionFlags,
) -> NativeTemplateExpansion | str:
    """Return the expansion, or `invalid` (Python raises) or `unsupported` (Python must run)."""

    try:
        outcome: tuple[object, list[tuple[str, str]]] | str = _native.expand_config_templates(
            value,
            (variables, os.environ, context_values),
            (flags.allow_context, flags.preserve_context_tokens, flags.preserve_unknown_context),
        )
    except TypeError:
        return UNSUPPORTED_OUTCOME
    if isinstance(outcome, str):
        return outcome
    return NativeTemplateExpansion(value=outcome[0], reads=tuple(outcome[1]))
