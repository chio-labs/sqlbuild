"""Public entrypoint for recursive template expansion."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.render.templating import (
    expand_template_data as _expand_template_data,
)
from sqlbuild.compiler.frontier.main._report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.types import NativeFallbackSite, NativeStage


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

    if native_stage_enabled(NativeStage.MODEL_CONFIG):
        report_native_fallback(site=NativeFallbackSite.PYTHON_TEMPLATES, kind="api")
    return _expand_template_data(
        value=value,
        variables=variables,
        context_values=context_values,
        context_label=context_label,
        allow_context=allow_context,
        preserve_context_tokens=preserve_context_tokens,
        preserve_unknown_context=preserve_unknown_context,
    )
