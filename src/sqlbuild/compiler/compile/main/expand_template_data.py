"""Public entrypoint for recursive template expansion."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.render.templating import (
    expand_template_data as _expand_template_data,
)


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

    return _expand_template_data(
        value,
        variables=variables,
        context_values=context_values,
        context_label=context_label,
        allow_context=allow_context,
        preserve_context_tokens=preserve_context_tokens,
        preserve_unknown_context=preserve_unknown_context,
    )
