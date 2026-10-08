"""Expand `${...}` templates in model config natively for the preview compiler engine."""

from __future__ import annotations

import os
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.model_config.constants import (
    NATIVE_TEMPLATE_REJECTION_LENGTH,
    UNSUPPORTED_OUTCOME,
)
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
    context_label: str | None = None,
) -> NativeTemplateExpansion | NativeTemplateRejection | str:
    """Return the expansion, a rejection (exact with `context_label`), or `unsupported`."""

    try:
        outcome: (
            tuple[object, list[tuple[str, str]]] | tuple[str, str, list[tuple[str, str]]] | str
        ) = _native.expand_config_templates(
            value,
            (variables, os.environ, context_values),
            (
                flags.allow_context,
                flags.preserve_context_tokens,
                flags.preserve_unknown_context,
                context_label,
            ),
        )
    except TypeError:
        return UNSUPPORTED_OUTCOME
    if isinstance(outcome, str):
        return outcome
    if len(outcome) == NATIVE_TEMPLATE_REJECTION_LENGTH:
        rejection: tuple[str, str, list[tuple[str, str]]] = cast(
            tuple[str, str, list[tuple[str, str]]], outcome
        )
        return NativeTemplateRejection(message=rejection[1], reads=tuple(rejection[2]))
    expansion: tuple[object, list[tuple[str, str]]] = cast(
        tuple[object, list[tuple[str, str]]], outcome
    )
    return NativeTemplateExpansion(value=expansion[0], reads=tuple(expansion[1]))
