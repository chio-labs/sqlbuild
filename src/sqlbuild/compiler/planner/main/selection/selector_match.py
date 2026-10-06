"""Public entrypoint matching one parsed selector before graph expansion."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner._helpers.graph.selectors import match_selector_keys
from sqlbuild.compiler.planner.models import ParsedSelector


def match_project_selector(
    *,
    parsed: ParsedSelector,
    all_keys: dict[str, CompiledObjectKey],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    """Return the keys one parsed selector matches before `+` graph expansion."""

    return match_selector_keys(
        parsed=parsed,
        all_keys=all_keys,
        tag_index=tag_index,
        path_index=path_index,
    )
