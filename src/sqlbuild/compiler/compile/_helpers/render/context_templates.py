"""Compile-time context and template resolution for model header values."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlbuild.compiler.compile._helpers.render.templating import expand_template_data
from sqlbuild.compiler.compile.types import CompileContextKey


def resolve_early_model_templates(
    *,
    values: dict[str, object],
    effective_vars: dict[str, object],
    effective_target_name: str | None,
    run_id: str,
) -> dict[str, object]:
    """Resolve `${name}`, `${ENV:...}`, and early `run.*` model templates."""

    return cast(
        dict[str, object],
        expand_config_templates(
            value=values,
            variables=effective_vars,
            context_values=build_run_context_values(
                effective_target_name=effective_target_name,
                run_id=run_id,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=True,
        ),
    )


def build_run_context_values(
    *, effective_target_name: str | None, run_id: str
) -> dict[str, str | None]:
    """Build the compile-time CTX values known before resource-specific resolution."""

    return {
        CompileContextKey.RUN_ID: run_id,
        CompileContextKey.RUN_TARGET: effective_target_name,
    }


def resolve_run_id(*, selected_run_id: str | None) -> str:
    """Resolve a stable compile invocation id."""

    if selected_run_id is not None:
        return selected_run_id
    timestamp_prefix: str = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    unique_suffix: str = uuid4().hex[:12]
    return f"{timestamp_prefix}_{unique_suffix}"


def expand_config_templates(
    *,
    value: object,
    variables: dict[str, object],
    context_values: dict[str, str | None],
    context_label: str,
    allow_context: bool,
    preserve_context_tokens: bool,
    preserve_unknown_context: bool,
) -> object:
    """Expand `${...}` templates in a config value natively, recording what it reads."""

    return expand_template_data(
        value=value,
        variables=variables,
        context_values=context_values,
        context_label=context_label,
        allow_context=allow_context,
        preserve_context_tokens=preserve_context_tokens,
        preserve_unknown_context=preserve_unknown_context,
    )
