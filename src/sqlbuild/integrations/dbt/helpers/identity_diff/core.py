"""dbt manifest identity diff helpers."""

from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import cast

from sqlbuild.integrations.dbt.constants import (
    DBT_DEFINITION_FINGERPRINT_EXCLUDED_CONFIG_KEYS,
    DBT_MANIFEST_CONFIG_KEY,
)
from sqlbuild.integrations.dbt.helpers.planning.model_identity import compose_dbt_version_hash
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSeed,
)
from sqlbuild.integrations.dbt.models import (
    DbtIdentityCause,
    DbtIdentityCausePath,
    DbtIdentityDiffResult,
    DbtIdentityInheritedOnly,
    DbtIdentityLocalDiff,
    DbtIdentitySelectedDiff,
)
from sqlbuild.integrations.dbt.types import DbtIdentityDiffReason, DbtIdentityDiffVerdict
from sqlbuild.shared.helpers.alignment import format_aligned_name_value, resolve_name_column_width
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.query_diff import format_query_diff


def build_dbt_identity_diff_result(
    *,
    current_manifest: DbtManifestIndex,
    ref_manifest: DbtManifestIndex,
    selected_unique_ids: Sequence[str],
    against: str,
    show_paths: bool = False,
    max_diff_lines: int = 2_000,
    max_diff_bytes: int = 200_000,
    on_progress: Callable[[str], None] | None = None,
) -> DbtIdentityDiffResult:
    """Build a set-based identity diff for selected dbt model IDs."""

    current_graph: dict[str, tuple[str, ...]] = _identity_upstreams(manifest=current_manifest)
    ref_graph: dict[str, tuple[str, ...]] = _identity_upstreams(manifest=ref_manifest)
    current_hashes: dict[str, str | None] = _version_hashes(
        manifest=current_manifest,
        graph=current_graph,
    )
    ref_hashes: dict[str, str | None] = _version_hashes(
        manifest=ref_manifest,
        graph=ref_graph,
    )
    local_diff_cache: dict[str, DbtIdentityLocalDiff | None] = {}
    selected_nodes: list[DbtIdentitySelectedDiff] = []
    selected_closures: dict[str, frozenset[str]] = {}
    cause_to_selected: dict[str, set[str]] = {}
    inherited_to_selected: dict[str, set[str]] = {}
    selected_total: int = len(selected_unique_ids)
    unique_id: str
    for index, unique_id in enumerate(selected_unique_ids, start=1):
        if on_progress is not None:
            on_progress(f"Diffing dbt identity for {unique_id} ({index}/{selected_total})...")
        current_hash: str | None = current_hashes.get(unique_id)
        ref_hash: str | None = ref_hashes.get(unique_id)
        if current_hash == ref_hash and current_hash is not None:
            selected_nodes.append(
                DbtIdentitySelectedDiff(
                    unique_id=unique_id,
                    name=_display_name(unique_id=unique_id, manifest=current_manifest),
                    verdict=DbtIdentityDiffVerdict.WOULD_REUSE,
                    current_version_hash=current_hash,
                    ref_version_hash=ref_hash,
                )
            )
            selected_closures[unique_id] = frozenset()
            continue
        closure: frozenset[str] = _changed_closure(
            unique_id=unique_id,
            current_graph=current_graph,
            ref_graph=ref_graph,
            current_hashes=current_hashes,
            ref_hashes=ref_hashes,
        )
        selected_closures[unique_id] = closure
        selected_causes: list[str] = []
        selected_inherited: list[str] = []
        changed_id: str
        for changed_id in sorted(
            closure, key=lambda node_id: _display_name(unique_id=node_id, manifest=current_manifest)
        ):
            local_diff: DbtIdentityLocalDiff | None = _cached_local_diff(
                unique_id=changed_id,
                current_manifest=current_manifest,
                ref_manifest=ref_manifest,
                current_graph=current_graph,
                ref_graph=ref_graph,
                cache=local_diff_cache,
                max_diff_lines=max_diff_lines,
                max_diff_bytes=max_diff_bytes,
                on_progress=on_progress,
            )
            if local_diff is None:
                selected_inherited.append(changed_id)
                inherited_to_selected.setdefault(changed_id, set()).add(unique_id)
                continue
            selected_causes.append(changed_id)
            cause_to_selected.setdefault(changed_id, set()).add(unique_id)
        selected_nodes.append(
            DbtIdentitySelectedDiff(
                unique_id=unique_id,
                name=_display_name(unique_id=unique_id, manifest=current_manifest),
                verdict=DbtIdentityDiffVerdict.REBUILD,
                current_version_hash=current_hash,
                ref_version_hash=ref_hash,
                causes=tuple(selected_causes),
                inherited_only=tuple(selected_inherited),
            )
        )
    causes: list[DbtIdentityCause] = []
    cause_id: str
    for cause_id in sorted(
        cause_to_selected,
        key=lambda node_id: _display_name(unique_id=node_id, manifest=current_manifest),
    ):
        local_diff = local_diff_cache[cause_id]
        if local_diff is None:
            continue
        causes.append(
            DbtIdentityCause(
                unique_id=cause_id,
                name=_display_name(unique_id=cause_id, manifest=current_manifest),
                current_version_hash=current_hashes.get(cause_id),
                ref_version_hash=ref_hashes.get(cause_id),
                local_diff=local_diff,
                affects_selected=tuple(sorted(cause_to_selected[cause_id])),
            )
        )
    inherited_only: list[DbtIdentityInheritedOnly] = []
    inherited_id: str
    for inherited_id in sorted(
        inherited_to_selected,
        key=lambda node_id: _display_name(unique_id=node_id, manifest=current_manifest),
    ):
        inherited_only.append(
            DbtIdentityInheritedOnly(
                unique_id=inherited_id,
                name=_display_name(unique_id=inherited_id, manifest=current_manifest),
                affects_selected=tuple(sorted(inherited_to_selected[inherited_id])),
            )
        )
    paths: tuple[DbtIdentityCausePath, ...] = ()
    if show_paths:
        paths = _cause_paths(
            selected_unique_ids=selected_unique_ids,
            cause_unique_ids=tuple(cause_to_selected),
            selected_closures=selected_closures,
            current_graph=current_graph,
            ref_graph=ref_graph,
            current_hashes=current_hashes,
            ref_hashes=ref_hashes,
        )
    return DbtIdentityDiffResult(
        selected=tuple(selected_nodes),
        causes=tuple(causes),
        inherited_only=tuple(inherited_only),
        paths=paths,
        against=against,
        warnings=(*current_manifest.seed_identity_warnings, *ref_manifest.seed_identity_warnings),
    )


def render_dbt_identity_diff_result(
    *,
    result: DbtIdentityDiffResult,
    quiet: bool,
    show_inherited: bool,
    show_paths: bool,
    use_color: bool,
) -> str:
    """Render a human-readable identity diff."""

    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [
        style.dbt_section("dbt identity diff") + f"  {style.muted('vs ' + result.against)}"
    ]
    name_column_width: int = _result_name_column_width(result=result)
    _append_selected_section(
        lines=lines,
        result=result,
        style=style,
        name_column_width=name_column_width,
    )
    if result.causes:
        _append_causes_section(
            lines=lines,
            result=result,
            style=style,
            quiet=quiet,
            name_column_width=name_column_width,
        )
    else:
        lines.append("")
        lines.append(style.success("No identity differences in selected models."))
    if show_paths and result.paths:
        _append_paths_section(lines=lines, result=result, style=style)
    _append_inherited_section(
        lines=lines,
        result=result,
        style=style,
        show_inherited=show_inherited,
        name_column_width=name_column_width,
    )
    if result.warnings:
        lines.append("")
        lines.append(style.warning_strong(f"Warnings ({len(result.warnings)})"))
        warning: str
        for warning in result.warnings:
            lines.append(f"  {style.warning('- ' + warning)}")
    return "\n".join(lines)


def format_dbt_identity_diff_json(result: DbtIdentityDiffResult) -> str:
    """Render identity diff as stable JSON."""

    payload: dict[str, object] = {
        "against": result.against,
        "selected": [_selected_json(selected) for selected in result.selected],
        "causes": [_cause_json(cause) for cause in result.causes],
        "inherited_only": [_inherited_json(inherited) for inherited in result.inherited_only],
        "paths": [_path_json(path) for path in result.paths],
        "warnings": list(result.warnings),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _local_diff(
    *,
    unique_id: str,
    current_manifest: DbtManifestIndex,
    ref_manifest: DbtManifestIndex,
    current_graph: Mapping[str, tuple[str, ...]],
    ref_graph: Mapping[str, tuple[str, ...]],
    max_diff_lines: int,
    max_diff_bytes: int,
    on_progress: Callable[[str], None] | None,
) -> DbtIdentityLocalDiff | None:
    current_model: DbtManifestModel | None = current_manifest.models_by_unique_id.get(unique_id)
    ref_model: DbtManifestModel | None = ref_manifest.models_by_unique_id.get(unique_id)
    if current_model is None:
        return DbtIdentityLocalDiff(
            unique_id=unique_id,
            reasons=(DbtIdentityDiffReason.MISSING_IN_CURRENT,),
        )
    if ref_model is None:
        return DbtIdentityLocalDiff(
            unique_id=unique_id,
            reasons=(DbtIdentityDiffReason.MISSING_IN_REF,),
        )
    reasons: list[DbtIdentityDiffReason] = []
    sql_diff: tuple[str, ...] = ()
    ref_sql: str = _authored_sql(ref_model)
    current_sql: str = _authored_sql(current_model)
    if ref_sql != current_sql:
        reasons.append(DbtIdentityDiffReason.QUERY)
        sql_diff = _safe_sql_diff(
            previous=ref_sql,
            current=current_sql,
            label=_display_name(unique_id=unique_id, manifest=current_manifest),
            max_diff_lines=max_diff_lines,
            max_diff_bytes=max_diff_bytes,
            on_progress=on_progress,
        )
    elif _compiled_sql(ref_model) != _compiled_sql(current_model):
        reasons.append(DbtIdentityDiffReason.COMPILED_ONLY)
        sql_diff = _safe_sql_diff(
            previous=_compiled_sql(ref_model),
            current=_compiled_sql(current_model),
            label=_display_name(unique_id=unique_id, manifest=current_manifest),
            max_diff_lines=max_diff_lines,
            max_diff_bytes=max_diff_bytes,
            on_progress=on_progress,
        )
    config_diff: tuple[str, ...] = _mapping_diff(
        previous=_identity_config(ref_model),
        current=_identity_config(current_model),
    )
    if config_diff:
        reasons.append(DbtIdentityDiffReason.CONFIG)
    schema_diff: tuple[str, ...] = _mapping_diff(
        previous=_columns_payload(ref_model),
        current=_columns_payload(current_model),
    )
    if schema_diff:
        reasons.append(DbtIdentityDiffReason.SCHEMA)
    current_upstreams: frozenset[str] = frozenset(current_graph.get(unique_id, ()))
    ref_upstreams: frozenset[str] = frozenset(ref_graph.get(unique_id, ()))
    upstream_added: tuple[str, ...] = tuple(sorted(current_upstreams - ref_upstreams))
    upstream_removed: tuple[str, ...] = tuple(sorted(ref_upstreams - current_upstreams))
    if upstream_added or upstream_removed:
        reasons.append(DbtIdentityDiffReason.UPSTREAM_SET)
    if not reasons:
        return None
    return DbtIdentityLocalDiff(
        unique_id=unique_id,
        reasons=tuple(dict.fromkeys(reasons)),
        sql_diff=sql_diff,
        config_diff=config_diff,
        schema_diff=schema_diff,
        upstream_added=upstream_added,
        upstream_removed=upstream_removed,
    )


def _cached_local_diff(
    *,
    unique_id: str,
    current_manifest: DbtManifestIndex,
    ref_manifest: DbtManifestIndex,
    current_graph: Mapping[str, tuple[str, ...]],
    ref_graph: Mapping[str, tuple[str, ...]],
    cache: dict[str, DbtIdentityLocalDiff | None],
    max_diff_lines: int,
    max_diff_bytes: int,
    on_progress: Callable[[str], None] | None,
) -> DbtIdentityLocalDiff | None:
    if unique_id not in cache:
        cache[unique_id] = _local_diff(
            unique_id=unique_id,
            current_manifest=current_manifest,
            ref_manifest=ref_manifest,
            current_graph=current_graph,
            ref_graph=ref_graph,
            max_diff_lines=max_diff_lines,
            max_diff_bytes=max_diff_bytes,
            on_progress=on_progress,
        )
    return cache[unique_id]


def _changed_closure(
    *,
    unique_id: str,
    current_graph: Mapping[str, tuple[str, ...]],
    ref_graph: Mapping[str, tuple[str, ...]],
    current_hashes: Mapping[str, str | None],
    ref_hashes: Mapping[str, str | None],
) -> frozenset[str]:
    changed: set[str] = set()
    stack: list[str] = [unique_id]
    while stack:
        current_id: str = stack.pop()
        if current_id in changed:
            continue
        if (
            current_hashes.get(current_id) == ref_hashes.get(current_id)
            and current_hashes.get(current_id) is not None
        ):
            continue
        changed.add(current_id)
        upstream_id: str
        for upstream_id in _upstream_union(
            unique_id=current_id,
            current_graph=current_graph,
            ref_graph=ref_graph,
        ):
            if current_hashes.get(upstream_id) != ref_hashes.get(upstream_id):
                stack.append(upstream_id)
    return frozenset(changed)


def _cause_paths(
    *,
    selected_unique_ids: Sequence[str],
    cause_unique_ids: tuple[str, ...],
    selected_closures: Mapping[str, frozenset[str]],
    current_graph: Mapping[str, tuple[str, ...]],
    ref_graph: Mapping[str, tuple[str, ...]],
    current_hashes: Mapping[str, str | None],
    ref_hashes: Mapping[str, str | None],
) -> tuple[DbtIdentityCausePath, ...]:
    cause_set: frozenset[str] = frozenset(cause_unique_ids)
    paths: list[DbtIdentityCausePath] = []
    selected_id: str
    for selected_id in selected_unique_ids:
        selected_causes: tuple[str, ...] = tuple(
            sorted(selected_closures.get(selected_id, frozenset()) & cause_set)
        )
        cause_id: str
        for cause_id in selected_causes:
            path: tuple[str, ...] | None = _representative_path(
                selected_unique_id=selected_id,
                cause_unique_id=cause_id,
                current_graph=current_graph,
                ref_graph=ref_graph,
                current_hashes=current_hashes,
                ref_hashes=ref_hashes,
            )
            if path is None:
                continue
            paths.append(
                DbtIdentityCausePath(
                    selected_unique_id=selected_id,
                    cause_unique_id=cause_id,
                    path=path,
                )
            )
    return tuple(paths)


def _representative_path(
    *,
    selected_unique_id: str,
    cause_unique_id: str,
    current_graph: Mapping[str, tuple[str, ...]],
    ref_graph: Mapping[str, tuple[str, ...]],
    current_hashes: Mapping[str, str | None],
    ref_hashes: Mapping[str, str | None],
) -> tuple[str, ...] | None:
    queue: deque[tuple[str, tuple[str, ...]]] = deque([(selected_unique_id, (selected_unique_id,))])
    seen: set[str] = set()
    while queue:
        unique_id, path = queue.popleft()
        if unique_id == cause_unique_id:
            return path
        if unique_id in seen:
            continue
        seen.add(unique_id)
        upstream_id: str
        for upstream_id in _upstream_union(
            unique_id=unique_id,
            current_graph=current_graph,
            ref_graph=ref_graph,
        ):
            if current_hashes.get(upstream_id) != ref_hashes.get(upstream_id):
                queue.append((upstream_id, (*path, upstream_id)))
    return None


def _upstream_union(
    *,
    unique_id: str,
    current_graph: Mapping[str, tuple[str, ...]],
    ref_graph: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    return _dedupe_sorted((*current_graph.get(unique_id, ()), *ref_graph.get(unique_id, ())))


def _version_hashes(
    *, manifest: DbtManifestIndex, graph: Mapping[str, tuple[str, ...]]
) -> dict[str, str | None]:
    cache: dict[str, str | None] = {}

    def version_hash(unique_id: str, stack: frozenset[str]) -> str | None:
        if unique_id in cache:
            return cache[unique_id]
        if unique_id in stack:
            return None
        own_hash: str | None = _own_hash(unique_id=unique_id, manifest=manifest)
        if own_hash is None:
            cache[unique_id] = None
            return None
        upstream_hashes: list[tuple[str, str]] = []
        upstream_id: str
        for upstream_id in graph.get(unique_id, ()):
            upstream_hash: str | None = version_hash(upstream_id, frozenset((*stack, unique_id)))
            if upstream_hash is not None:
                upstream_hashes.append((upstream_id, upstream_hash))
        cache[unique_id] = compose_dbt_version_hash(
            own_hash=own_hash,
            upstream_hashes=tuple(upstream_hashes),
        )
        return cache[unique_id]

    unique_id: str
    for unique_id in (*manifest.seeds_by_unique_id, *manifest.models_by_unique_id):
        version_hash(unique_id, frozenset())
    return cache


def _identity_upstreams(*, manifest: DbtManifestIndex) -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {unique_id: () for unique_id in manifest.seeds_by_unique_id}
    unique_id: str
    model: DbtManifestModel
    for unique_id, model in manifest.models_by_unique_id.items():
        graph[unique_id] = tuple(
            dep
            for dep in model.depends_on_nodes
            if dep in manifest.models_by_unique_id or dep in manifest.seeds_by_unique_id
        )
    return graph


def _safe_sql_diff(
    *,
    previous: str,
    current: str,
    label: str,
    max_diff_lines: int,
    max_diff_bytes: int,
    on_progress: Callable[[str], None] | None,
) -> tuple[str, ...]:
    previous_lines: tuple[str, ...] = tuple(previous.splitlines())
    current_lines: tuple[str, ...] = tuple(current.splitlines())
    previous_size: int = len(previous.encode("utf-8"))
    current_size: int = len(current.encode("utf-8"))
    prefix_count: int = _common_prefix_count(
        previous_lines=previous_lines,
        current_lines=current_lines,
    )
    suffix_count: int = _common_suffix_count(
        previous_lines=previous_lines,
        current_lines=current_lines,
        prefix_count=prefix_count,
    )
    previous_middle: tuple[str, ...] = _middle_lines(
        lines=previous_lines,
        prefix_count=prefix_count,
        suffix_count=suffix_count,
    )
    current_middle: tuple[str, ...] = _middle_lines(
        lines=current_lines,
        prefix_count=prefix_count,
        suffix_count=suffix_count,
    )
    middle_chars: int = sum(len(line) + 1 for line in (*previous_middle, *current_middle))
    middle_lines: int = len(previous_middle) + len(current_middle)
    if middle_chars > max_diff_bytes or middle_lines > max_diff_lines:
        return (
            _format_suppressed_sql_diff(
                previous_size=previous_size,
                current_size=current_size,
                previous_lines=len(previous_lines),
                current_lines=len(current_lines),
                middle_chars=middle_chars,
                middle_lines=middle_lines,
                max_diff_bytes=max_diff_bytes,
                max_diff_lines=max_diff_lines,
            ),
        )
    if on_progress is not None:
        start: float = time.monotonic()
        on_progress(
            _format_sql_diff_progress(
                label=label,
                previous_size=previous_size,
                current_size=current_size,
            )
        )
    diff_lines: list[str] = []
    if prefix_count:
        diff_lines.append(f"... {prefix_count} unchanged prefix line(s) ...")
    diff_lines.extend(format_query_diff("\n".join(previous_middle), "\n".join(current_middle)))
    if suffix_count:
        diff_lines.append(f"... {suffix_count} unchanged suffix line(s) ...")
    if on_progress is not None:
        on_progress(f"Rendered SQL diff for {label}. ({time.monotonic() - start:.2f}s)")
    return tuple(diff_lines)


def _common_prefix_count(*, previous_lines: tuple[str, ...], current_lines: tuple[str, ...]) -> int:
    count: int = 0
    for previous_line, current_line in zip(previous_lines, current_lines, strict=False):
        if previous_line != current_line:
            return count
        count += 1
    return count


def _common_suffix_count(
    *, previous_lines: tuple[str, ...], current_lines: tuple[str, ...], prefix_count: int
) -> int:
    count: int = 0
    max_count: int = min(len(previous_lines), len(current_lines)) - prefix_count
    while count < max_count:
        if previous_lines[-count - 1] != current_lines[-count - 1]:
            return count
        count += 1
    return count


def _middle_lines(
    *, lines: tuple[str, ...], prefix_count: int, suffix_count: int
) -> tuple[str, ...]:
    end_index: int = len(lines) - suffix_count if suffix_count else len(lines)
    return lines[prefix_count:end_index]


def _format_sql_diff_progress(*, label: str, previous_size: int, current_size: int) -> str:
    return (
        f"Rendering SQL diff for {label} "
        f"({_format_bytes(previous_size)} -> {_format_bytes(current_size)})..."
    )


def _format_suppressed_sql_diff(
    *,
    previous_size: int,
    current_size: int,
    previous_lines: int,
    current_lines: int,
    middle_chars: int,
    middle_lines: int,
    max_diff_bytes: int,
    max_diff_lines: int,
) -> str:
    return (
        "SQL differs "
        f"({_format_bytes(previous_size)} -> {_format_bytes(current_size)}, "
        f"{previous_lines} -> {current_lines} lines); "
        "full diff suppressed because the changed region is too large "
        f"({_format_bytes(middle_chars)}, {middle_lines} lines). "
        "Raise --max-diff-bytes or --max-diff-lines to show more. "
        f"Current limits: {_format_bytes(max_diff_bytes)}, {max_diff_lines} lines."
    )


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    return f"{size / 1024:.1f} KB"


def _own_hash(*, unique_id: str, manifest: DbtManifestIndex) -> str | None:
    seed: DbtManifestSeed | None = manifest.seeds_by_unique_id.get(unique_id)
    if seed is not None:
        return seed.identity_hash
    model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
    if model is None:
        return None
    return model.node_checksum or hashlib.sha256(model.query_sql.encode("utf-8")).hexdigest()


def _append_selected_section(
    *,
    lines: list[str],
    result: DbtIdentityDiffResult,
    style: CliStyle,
    name_column_width: int,
) -> None:
    lines.append("")
    lines.append(style.plan_section(f"Selected ({len(result.selected)})"))
    cause_by_id: dict[str, DbtIdentityCause] = {cause.unique_id: cause for cause in result.causes}
    selected: DbtIdentitySelectedDiff
    for selected in result.selected:
        lines.append(
            _format_name_value_line(
                selected.name,
                _styled_verdict(selected.verdict, style=style),
                style=style,
                name_column_width=name_column_width,
            )
        )
        if selected.verdict == DbtIdentityDiffVerdict.WOULD_REUSE:
            lines.append(f"    {style.muted('identity:')} equal")
            continue
        if selected.causes:
            cause_labels: str = ", ".join(
                _selected_cause_label(cause_by_id[cause_id], style=style)
                for cause_id in selected.causes
                if cause_id in cause_by_id
            )
            lines.append(f"    cause: {cause_labels}")
        else:
            lines.append(f"    cause: {style.muted('none found')}")
        lines.append(f"    inherited-only: {len(selected.inherited_only)} node(s)")


def _append_causes_section(
    *,
    lines: list[str],
    result: DbtIdentityDiffResult,
    style: CliStyle,
    quiet: bool,
    name_column_width: int,
) -> None:
    lines.append("")
    lines.append(style.plan_section(f"Causes ({len(result.causes)})"))
    cause: DbtIdentityCause
    for cause in result.causes:
        lines.append(
            _format_name_value_line(
                cause.name,
                _styled_reasons(cause.local_diff.reasons, style=style),
                style=style,
                name_column_width=name_column_width,
            )
        )
        affects: str = ", ".join(
            _display_id_name(unique_id) for unique_id in cause.affects_selected
        )
        lines.append(f"    affects: {affects}")
        if not quiet:
            _append_local_diff(lines=lines, diff=cause.local_diff, style=style, indent="    ")


def _append_paths_section(
    *, lines: list[str], result: DbtIdentityDiffResult, style: CliStyle
) -> None:
    lines.append("")
    lines.append(style.plan_section(f"Cause paths ({len(result.paths)})"))
    path: DbtIdentityCausePath
    for path in result.paths:
        lines.append(f"  {' <- '.join(_display_id_name(unique_id) for unique_id in path.path)}")


def _append_inherited_section(
    *,
    lines: list[str],
    result: DbtIdentityDiffResult,
    style: CliStyle,
    show_inherited: bool,
    name_column_width: int,
) -> None:
    if not result.inherited_only:
        return
    lines.append("")
    lines.append(style.plan_section(f"Inherited only ({len(result.inherited_only)})"))
    if not show_inherited:
        lines.append("  distinct node(s) differ only through upstream identity.")
        lines.append(f"  {style.muted('Use --show-inherited to list them.')}")
        return
    inherited: DbtIdentityInheritedOnly
    for inherited in result.inherited_only:
        lines.append(
            _format_name_value_line(
                inherited.name,
                style.muted("upstream only"),
                style=style,
                name_column_width=name_column_width,
            )
        )
        affects: str = ", ".join(
            _display_id_name(unique_id) for unique_id in inherited.affects_selected
        )
        lines.append(f"    affects: {affects}")


def _format_name_value_line(
    plain_name: str,
    value: str,
    *,
    style: CliStyle,
    name_column_width: int,
) -> str:
    return format_aligned_name_value(
        plain_name=plain_name,
        styled_name=style.dbt_object_name(plain_name),
        value=value,
        name_column_width=name_column_width,
    )


def _append_local_diff(
    *, lines: list[str], diff: DbtIdentityLocalDiff, style: CliStyle, indent: str
) -> None:
    if diff.upstream_added or diff.upstream_removed:
        lines.append(f"{indent}{style.warning('upstream set diff:')}")
        upstream_id: str
        for upstream_id in diff.upstream_removed:
            lines.append(f"{indent}  {style.error('- ' + upstream_id)}")
        for upstream_id in diff.upstream_added:
            lines.append(f"{indent}  {style.success('+ ' + upstream_id)}")
    if diff.config_diff:
        lines.append(f"{indent}{style.warning('config diff:')}")
        lines.extend(f"{indent}  {line}" for line in diff.config_diff)
    if diff.schema_diff:
        lines.append(f"{indent}{style.warning('schema diff:')}")
        lines.extend(f"{indent}  {line}" for line in diff.schema_diff)
    if diff.sql_diff:
        lines.append(f"{indent}{style.warning('sql diff:')}")
        lines.extend(f"{indent}{line}" for line in diff.sql_diff)


def _styled_verdict(verdict: DbtIdentityDiffVerdict, *, style: CliStyle) -> str:
    if verdict == DbtIdentityDiffVerdict.WOULD_REUSE:
        return style.success_strong("WOULD-REUSE")
    if verdict == DbtIdentityDiffVerdict.CAUSE:
        return style.warning_strong("CAUSE")
    if verdict == DbtIdentityDiffVerdict.UPSTREAM_ONLY:
        return style.warning("UPSTREAM only")
    return style.warning_strong("REBUILD")


def _styled_reasons(reasons: tuple[DbtIdentityDiffReason, ...], *, style: CliStyle) -> str:
    if reasons == (DbtIdentityDiffReason.UPSTREAM_ONLY,):
        return style.warning("upstream only") + " " + style.muted("(own content same)")
    return ", ".join(style.warning(reason.value.replace("_", " ")) for reason in reasons)


def _selected_cause_label(cause: DbtIdentityCause, *, style: CliStyle) -> str:
    return f"{style.dbt_object_name(cause.name)} ({_reason_label(cause.local_diff.reasons)})"


def _reason_label(reasons: tuple[DbtIdentityDiffReason, ...]) -> str:
    return "+".join(reason.value for reason in reasons)


def _selected_json(selected: DbtIdentitySelectedDiff) -> dict[str, object]:
    return {
        "unique_id": selected.unique_id,
        "name": selected.name,
        "verdict": selected.verdict.value,
        "current_version_hash": selected.current_version_hash,
        "ref_version_hash": selected.ref_version_hash,
        "causes": list(selected.causes),
        "inherited_only": list(selected.inherited_only),
    }


def _cause_json(cause: DbtIdentityCause) -> dict[str, object]:
    return {
        "unique_id": cause.unique_id,
        "name": cause.name,
        "current_version_hash": cause.current_version_hash,
        "ref_version_hash": cause.ref_version_hash,
        "affects_selected": list(cause.affects_selected),
        "local_diff": _local_diff_json(cause.local_diff),
    }


def _inherited_json(inherited: DbtIdentityInheritedOnly) -> dict[str, object]:
    return {
        "unique_id": inherited.unique_id,
        "name": inherited.name,
        "affects_selected": list(inherited.affects_selected),
    }


def _path_json(path: DbtIdentityCausePath) -> dict[str, object]:
    return {
        "selected_unique_id": path.selected_unique_id,
        "cause_unique_id": path.cause_unique_id,
        "path": list(path.path),
    }


def _local_diff_json(diff: DbtIdentityLocalDiff) -> dict[str, object]:
    return {
        "unique_id": diff.unique_id,
        "reasons": [reason.value for reason in diff.reasons],
        "sql_diff": list(diff.sql_diff),
        "config_diff": list(diff.config_diff),
        "schema_diff": list(diff.schema_diff),
        "upstream_added": list(diff.upstream_added),
        "upstream_removed": list(diff.upstream_removed),
    }


def _result_name_column_width(*, result: DbtIdentityDiffResult) -> int:
    names: list[str] = [selected.name for selected in result.selected]
    names.extend(cause.name for cause in result.causes)
    names.extend(inherited.name for inherited in result.inherited_only)
    return resolve_name_column_width(tuple(names), min_width=28)


def _display_id_name(unique_id: str) -> str:
    return unique_id.rsplit(".", maxsplit=1)[-1]


def _display_name(*, unique_id: str, manifest: DbtManifestIndex) -> str:
    model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
    if model is not None:
        return model.name
    seed: DbtManifestSeed | None = manifest.seeds_by_unique_id.get(unique_id)
    if seed is not None:
        return seed.name
    return unique_id.rsplit(".", maxsplit=1)[-1]


def _authored_sql(model: DbtManifestModel) -> str:
    return (
        _payload_str(model.payload, "raw_code")
        or _payload_str(model.payload, "raw_sql")
        or model.query_sql
    )


def _compiled_sql(model: DbtManifestModel) -> str:
    return (
        _payload_str(model.payload, "compiled_code")
        or _payload_str(model.payload, "compiled_sql")
        or model.query_sql
    )


def _identity_config(model: DbtManifestModel) -> dict[str, object]:
    raw_config: object | None = model.payload.get(DBT_MANIFEST_CONFIG_KEY)
    if not isinstance(raw_config, dict):
        return {}
    return {
        str(key): _normalize_json_value(value)
        for key, value in raw_config.items()
        if str(key) not in DBT_DEFINITION_FINGERPRINT_EXCLUDED_CONFIG_KEYS
    }


def _columns_payload(model: DbtManifestModel) -> dict[str, object]:
    raw_columns: object | None = model.payload.get("columns")
    if not isinstance(raw_columns, dict):
        return {}
    return {str(key): _normalize_json_value(value) for key, value in raw_columns.items()}


def _mapping_diff(
    *, previous: Mapping[str, object], current: Mapping[str, object]
) -> tuple[str, ...]:
    lines: list[str] = []
    key: str
    for key in sorted(frozenset((*previous.keys(), *current.keys()))):
        previous_value: object = previous.get(key)
        current_value: object = current.get(key)
        if previous_value == current_value:
            continue
        if key in previous and key not in current:
            lines.append(f"- {key}: {_json_dump(previous_value)}")
        elif key in current and key not in previous:
            lines.append(f"+ {key}: {_json_dump(current_value)}")
        else:
            lines.append(f"- {key}: {_json_dump(previous_value)}")
            lines.append(f"+ {key}: {_json_dump(current_value)}")
    return tuple(lines)


def _normalize_json_value(value: object) -> object:
    if isinstance(value, dict):
        mapping: dict[object, object] = cast(dict[object, object], value)
        return {str(key): _normalize_json_value(mapping[key]) for key in sorted(mapping, key=str)}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return value


def _json_dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _payload_str(payload: Mapping[str, object], key: str) -> str | None:
    value: object | None = payload.get(key)
    return value if isinstance(value, str) and value else None


def _dedupe_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(dict.fromkeys(values)))
