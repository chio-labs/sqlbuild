"""Selector parsing and scope resolution for planner graph selection."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.graph import (
    expand_downstream,
    expand_upstream,
    find_path_keys,
)
from sqlbuild.compiler.planner.models import ParsedSelector, PathSelector
from sqlbuild.compiler.planner.types import SelectorKind

_SELECTOR_KIND_BY_PREFIX: dict[str, SelectorKind] = {
    SelectorKind.SEED: SelectorKind.SEED,
    SelectorKind.SOURCE: SelectorKind.SOURCE,
    SelectorKind.TAG: SelectorKind.TAG,
    SelectorKind.PATH: SelectorKind.PATH,
}

_RESOURCE_TYPE_BY_SELECTOR_KIND: dict[SelectorKind, CompiledResourceType] = {
    SelectorKind.SEED: CompiledResourceType.SEED,
    SelectorKind.SOURCE: CompiledResourceType.SOURCE,
}


def parse_selector(raw: str) -> ParsedSelector | PathSelector:
    """Parse one raw selector token into a structured form.

    Returns a ParsedSelector for normal selectors, or a (start, end) tuple
    for path selectors using the a~b syntax.
    """

    stripped: str = raw.strip()
    if not stripped:
        raise PlannerInputError("empty selector", code="S001")

    upstream: bool = stripped.startswith("+")
    downstream: bool = stripped.endswith("+")
    core: str = stripped.lstrip("+").rstrip("+")

    if "~" in core:
        if "+" in core:
            raise PlannerInputError(
                f"selector '{stripped}' contains '+' in an unsupported position",
                code="S002",
            )
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
    if not name:
        raise PlannerInputError(
            f"selector '{stripped}' has no name after removing '+' markers",
            code="S004",
        )
    if "+" in name:
        raise PlannerInputError(
            f"selector '{stripped}' contains '+' in an unsupported position",
            code="S002",
        )

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
    """Resolve raw select/exclude strings into a final set of object keys.

    Multiple --select values and space-separated tokens within one --select
    are unioned. Comma within a token means intersection. --exclude is
    subtracted from the union.
    """

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

    scoped: set[CompiledObjectKey] = selected - excluded
    key: CompiledObjectKey
    for key in tuple(scoped):
        upstream_key: CompiledObjectKey
        for upstream_key in expand_upstream(key, upstream):
            if upstream_key.resource_type == CompiledResourceType.FUNCTION:
                scoped.add(upstream_key)
    return frozenset(scoped)


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

    folder: str = parsed.value
    prefix: str = folder + "/"
    matched_keys: frozenset[CompiledObjectKey] = frozenset(
        key
        for key, model_folder in path_index.items()
        if model_folder == folder or model_folder.startswith(prefix)
    )
    if not matched_keys:
        hint: str = ""
        if folder.startswith("models/"):
            stripped_folder: str = folder[len("models/") :]
            hint = (
                f" (the 'models/' prefix is stripped automatically - try 'path:{stripped_folder}')"
            )
        raise PlannerInputError(f"no models found under path '{folder}'.{hint}", code="S009")

    result: set[CompiledObjectKey] = set(matched_keys)
    key: CompiledObjectKey
    if parsed.upstream:
        for key in matched_keys:
            result.update(expand_upstream(key, upstream))
    if parsed.downstream:
        for key in matched_keys:
            result.update(expand_downstream(key, downstream))
    return frozenset(result)


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
