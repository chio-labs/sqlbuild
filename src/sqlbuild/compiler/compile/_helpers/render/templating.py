"""Template expansion for compile inputs, natively, with the reads it makes recorded."""

from __future__ import annotations

from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.classes.unicode_environment import UnicodeEnvironment
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.model_config.constants import ENVIRONMENT_READ
from sqlbuild.compiler.model_config.main._expand_native_config_templates import (
    expand_native_config_templates,
)
from sqlbuild.compiler.model_config.main._native_config_error import native_config_error
from sqlbuild.compiler.model_config.models import (
    NativeTemplateExpansion,
    NativeTemplateRejection,
    TemplateResolutionFlags,
)


def expand_effective_vars(raw_values: dict[str, object]) -> dict[str, object]:
    """Resolve merged effective vars with recursive `${name}` expansion."""

    site: tuple[str, str, int] | None = _native.lone_surrogate_site(raw_values)
    if site is not None:
        name, path, byte_offset = site
        raise CompileInputError(
            f"Variable '{name}' holds a lone surrogate in {path} at UTF-8 byte "
            f"{byte_offset}, which is not valid Unicode text",
            help=(
                f"Set '{name}' to valid Unicode text in --vars or the [vars] table; the "
                "value is not shown because it may be a secret"
            ),
        )
    outcome: tuple[object, list[tuple[str, str]]] = _native.expand_effective_vars(
        raw_values, UnicodeEnvironment()
    )
    record_template_reads(tuple(outcome[1]))
    if isinstance(outcome[0], _native.NativeConfigError):
        raise native_config_error(error=outcome[0])
    return cast(dict[str, object], outcome[0])


def expand_template_data(
    *,
    value: object,
    variables: dict[str, object],
    context_values: dict[str, str | None],
    context_label: str,
    allow_context: bool,
    preserve_context_tokens: bool,
    preserve_unknown_context: bool,
) -> object:
    """Recursively expand template strings inside supported Python container values."""

    outcome: NativeTemplateExpansion | NativeTemplateRejection = expand_native_config_templates(
        value=value,
        variables=variables,
        context_values=context_values,
        flags=TemplateResolutionFlags(
            allow_context=allow_context,
            preserve_context_tokens=preserve_context_tokens,
            preserve_unknown_context=preserve_unknown_context,
        ),
        context_label=context_label,
    )
    record_template_reads(outcome.reads)
    if isinstance(outcome, NativeTemplateRejection):
        raise native_config_error(error=outcome.error)
    return outcome.value


def record_template_reads(reads: tuple[tuple[str, str], ...]) -> None:
    """Record native template environment and context reads for project reuse, in order."""

    for kind, name in reads:
        if kind == ENVIRONMENT_READ:
            COMPILE_INPUT_READS.environment_read(name)
        else:
            COMPILE_INPUT_READS.context_read(name)
