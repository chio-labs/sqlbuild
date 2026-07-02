"""Selector parsing and scope resolution for planner graph selection."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.graph.core import (
    expand_downstream,
    expand_upstream,
    find_path_keys,
)
from sqlbuild.compiler.planner.main.planning.selector_expansion import split_selector_expansion
from sqlbuild.compiler.planner.models import ParsedSelector, PathSelector
from sqlbuild.compiler.planner.types import SelectorKind
from sqlbuild.shared.exceptions.errors import SharedInputError
from sqlbuild.shared.models import SelectorExpansion

_SELECTOR_KIND_BY_PREFIX: dict[str, SelectorKind] = {
    SelectorKind.SEED: SelectorKind.SEED,
    SelectorKind.SOURCE: SelectorKind.SOURCE,
    SelectorKind.TASK: SelectorKind.TASK,
    SelectorKind.ASSET: SelectorKind.ASSET,
    SelectorKind.LOADER: SelectorKind.LOADER,
    SelectorKind.CHECK: SelectorKind.CHECK,
    SelectorKind.TAG: SelectorKind.TAG,
    SelectorKind.PATH: SelectorKind.PATH,
}

_RESOURCE_TYPE_BY_SELECTOR_KIND: dict[SelectorKind, CompiledResourceType] = {
    SelectorKind.SEED: CompiledResourceType.SEED,
    SelectorKind.SOURCE: CompiledResourceType.SOURCE,
}


def parse_selector(raw: str) -> ParsedSelector | PathSelector:
    """Parse one raw selector token into a structured form."""

    stripped: str = raw.strip()
    try:
        expansion: SelectorExpansion = split_selector_expansion(raw)
    except SharedInputError as error:
        code: str = "S001" if not stripped else "S002"
        if "no name" in str(error):
            code = "S004"
        raise PlannerInputError(str(error), code=code) from None

    upstream: bool = expansion.upstream
    downstream: bool = expansion.downstream
    core: str = expansion.core

    if "~" in core:
        parts: list[str] = core.split("~", 1)
        start_name: str = parts[0].strip()
        end_name: str = parts[1].strip()
        if not start_name or not end_name:
            raise PlannerInputError(
                f"path selector '{stripped}' requires names on both sides of '~'",
                code="S003",
            )
        return PathSelector(
            start_name=start_name,
            end_name=end_name,
            upstream=upstream,
            downstream=downstream,
        )

    name: str = core
    if ":" in name:
        prefix: str
        value: str
        prefix, value = name.split(":", 1)
        kind: SelectorKind | None = _SELECTOR_KIND_BY_PREFIX.get(prefix)
        if kind is None:
            raise PlannerInputError(
                f"unknown selector type '{prefix}' in '{stripped}'", code="S005"
            )
        if not value:
            raise PlannerInputError(f"selector '{stripped}' has empty value after ':'", code="S006")
        return ParsedSelector(kind=kind, value=value, upstream=upstream, downstream=downstream)

    if "/" in name:
        folder_value: str = name.strip("/")
        return ParsedSelector(
            kind=SelectorKind.PATH, value=folder_value, upstream=upstream, downstream=downstream
        )

    return ParsedSelector(
        kind=SelectorKind.NAME, value=name, upstream=upstream, downstream=downstream
    )


def resolve_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    all_keys: dict[str, CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]] | None = None,
    path_index: dict[CompiledObjectKey, str] | None = None,
) -> frozenset[CompiledObjectKey]:
    """Resolve raw select/exclude strings into a final set of object keys."""

    effective_tag_index: dict[str, frozenset[CompiledObjectKey]] = tag_index or {}
    effective_path_index: dict[CompiledObjectKey, str] = path_index or {}

    if not select:
        return frozenset(all_keys.values())

    selected: set[CompiledObjectKey] = set()
    raw_select: str
    for raw_select in select:
        tokens: list[str] = raw_select.split()
        token: str
        for token in tokens:
            resolved: frozenset[CompiledObjectKey] = _resolve_token(
                token=token,
                all_keys=all_keys,
                upstream=upstream,
                downstream=downstream,
                tag_index=effective_tag_index,
                path_index=effective_path_index,
            )
            selected.update(resolved)

    excluded: set[CompiledObjectKey] = set()
    raw_exclude: str
    for raw_exclude in exclude:
        tokens = raw_exclude.split()
        for token in tokens:
            resolved = _resolve_token(
                token=token,
                all_keys=all_keys,
                upstream=upstream,
                downstream=downstream,
                tag_index=effective_tag_index,
                path_index=effective_path_index,
            )
            excluded.update(resolved)

    scoped: frozenset[CompiledObjectKey] = frozenset(selected - excluded)
    return expand_required_build_resources(
        selected_keys=scoped,
        upstream=upstream,
        downstream=downstream,
        include_upstream_functions=True,
        include_upstream_seeds=False,
        include_downstream_functions=False,
    )


def expand_required_build_resources(
    *,
    selected_keys: frozenset[CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    include_upstream_functions: bool = True,
    include_upstream_seeds: bool = False,
    include_downstream_functions: bool = False,
) -> frozenset[CompiledObjectKey]:
    """Add non-model resources needed to build a coherent selected model scope."""

    expanded: set[CompiledObjectKey] = set(selected_keys)
    key: CompiledObjectKey
    for key in tuple(selected_keys):
        upstream_key: CompiledObjectKey
        for upstream_key in expand_upstream(key, upstream):
            if include_upstream_functions and upstream_key.resource_type in {
                CompiledResourceType.UDF,
                CompiledResourceType.TABLE_FN,
            }:
                expanded.add(upstream_key)
            if include_upstream_seeds and upstream_key.resource_type == CompiledResourceType.SEED:
                expanded.add(upstream_key)
    if not include_downstream_functions:
        return frozenset(expanded)
    selected_model_keys: frozenset[CompiledObjectKey] = frozenset(
        key for key in selected_keys if key.resource_type == CompiledResourceType.MODEL
    )
    for key in selected_model_keys:
        downstream_key: CompiledObjectKey
        for downstream_key in downstream.get(key, ()):
            if downstream_key.resource_type in {
                CompiledResourceType.UDF,
                CompiledResourceType.TABLE_FN,
            }:
                expanded.add(downstream_key)
    return frozenset(expanded)


def _resolve_token(
    *,
    token: str,
    all_keys: dict[str, CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    """Resolve one selector token, handling comma intersection."""

    parts: list[str] = token.split(",")
    if len(parts) == 1:
        return _resolve_single(
            raw=parts[0],
            all_keys=all_keys,
            upstream=upstream,
            downstream=downstream,
            tag_index=tag_index,
            path_index=path_index,
        )

    sets: list[frozenset[CompiledObjectKey]] = [
        _resolve_single(
            raw=part,
            all_keys=all_keys,
            upstream=upstream,
            downstream=downstream,
            tag_index=tag_index,
            path_index=path_index,
        )
        for part in parts
    ]
    result: frozenset[CompiledObjectKey] = sets[0]
    subsequent: frozenset[CompiledObjectKey]
    for subsequent in sets[1:]:
        result = result & subsequent
    return result


def _resolve_single(
    *,
    raw: str,
    all_keys: dict[str, CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    """Resolve one atomic selector (no commas)."""

    parsed: ParsedSelector | PathSelector = parse_selector(raw)

    if isinstance(parsed, PathSelector):
        start_name: str = parsed.start_name
        end_name: str = parsed.end_name
        start_key: CompiledObjectKey | None = all_keys.get(start_name)
        end_key: CompiledObjectKey | None = all_keys.get(end_name)
        if start_key is None:
            raise PlannerInputError(f"unknown selector name '{start_name}'", code="S007")
        if end_key is None:
            raise PlannerInputError(f"unknown selector name '{end_name}'", code="S007")
        result: set[CompiledObjectKey] = set(find_path_keys(start_key, end_key, downstream))
        if parsed.upstream:
            result.update(expand_upstream(start_key, upstream))
        if parsed.downstream:
            result.update(expand_downstream(end_key, downstream))
        return frozenset(result)

    if parsed.kind == SelectorKind.TAG:
        return _resolve_tag(
            parsed=parsed,
            tag_index=tag_index,
            upstream=upstream,
            downstream=downstream,
        )

    if parsed.kind == SelectorKind.PATH:
        return _resolve_path(
            parsed=parsed,
            path_index=path_index,
            upstream=upstream,
            downstream=downstream,
        )

    key: CompiledObjectKey | None = _lookup_key(parsed, all_keys)
    if key is None:
        raise PlannerInputError(f"unknown selector name '{parsed.value}'", code="S007")

    result: set[CompiledObjectKey] = {key}
    if parsed.upstream:
        result.update(expand_upstream(key, upstream))
    if parsed.downstream:
        result.update(expand_downstream(key, downstream))
    return frozenset(result)


def _resolve_tag(
    *,
    parsed: ParsedSelector,
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Resolve a tag selector to matching keys with optional graph expansion."""

    tagged_keys: frozenset[CompiledObjectKey] = tag_index.get(parsed.value, frozenset())
    if not tagged_keys:
        raise PlannerInputError(f"no models found with tag '{parsed.value}'", code="S008")

    result: set[CompiledObjectKey] = set(tagged_keys)
    key: CompiledObjectKey
    if parsed.upstream:
        for key in tagged_keys:
            result.update(expand_upstream(key, upstream))
    if parsed.downstream:
        for key in tagged_keys:
            result.update(expand_downstream(key, downstream))
    return frozenset(result)


def _resolve_path(
    *,
    parsed: ParsedSelector,
    path_index: dict[CompiledObjectKey, str],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Resolve a path selector to matching keys with optional graph expansion."""

    folder: str = _normalize_path_selector_value(parsed.value)
    selector_folder: str = _model_path_candidate(folder)
    matched_keys: frozenset[CompiledObjectKey] = frozenset(
        key
        for key, indexed_folder in path_index.items()
        if _path_matches(indexed_folder, selector_folder)
    )
    if not matched_keys:
        raise PlannerInputError(f"no models found under path '{folder}'.", code="S009")

    result: set[CompiledObjectKey] = set(matched_keys)
    key: CompiledObjectKey
    if parsed.upstream:
        for key in matched_keys:
            result.update(expand_upstream(key, upstream))
    if parsed.downstream:
        for key in matched_keys:
            result.update(expand_downstream(key, downstream))
    return frozenset(result)


def _normalize_path_selector_value(value: str) -> str:
    return value.replace("\\", "/").strip("/")


def _model_path_candidate(folder: str) -> str:
    if folder == "models":
        return ""
    if folder.startswith("models/"):
        return folder[len("models/") :]
    raise PlannerInputError(
        "path selectors require an explicit root: use 'models/', 'tasks/', 'assets/', "
        "'checks/', or 'loaders/'",
        code="S012",
    )


def _path_matches(indexed_folder: str, selector_folder: str) -> bool:
    if selector_folder == "":
        return True
    return indexed_folder == selector_folder or indexed_folder.startswith(f"{selector_folder}/")


def _lookup_key(
    parsed: ParsedSelector,
    all_keys: dict[str, CompiledObjectKey],
) -> CompiledObjectKey | None:
    """Look up the object key for a parsed selector."""

    if parsed.kind == SelectorKind.NAME:
        return all_keys.get(parsed.value)

    resource_type: CompiledResourceType | None = _RESOURCE_TYPE_BY_SELECTOR_KIND.get(parsed.kind)
    if resource_type is None:
        raise PlannerInputError(
            f"selector type '{parsed.kind}' does not map to a resource type yet",
            code="S010",
        )

    candidate: CompiledObjectKey | None = all_keys.get(parsed.value)
    if candidate is not None and candidate.resource_type == resource_type:
        return candidate
    return None
