"""dbt manifest identity diff helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
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
    DbtIdentityDiffNode,
    DbtIdentityDiffResult,
    DbtIdentityLocalDiff,
)
from sqlbuild.integrations.dbt.types import DbtIdentityDiffReason, DbtIdentityDiffVerdict
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.query_diff import format_query_diff


def build_dbt_identity_diff_result(
    *,
    current_manifest: DbtManifestIndex,
    ref_manifest: DbtManifestIndex,
    selected_unique_ids: Sequence[str],
    against: str,
    depth: int | None = None,
) -> DbtIdentityDiffResult:
    """Build an identity diff tree for selected dbt model IDs."""

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
    selected_nodes: list[DbtIdentityDiffNode] = []
    causes_by_unique_id: dict[str, DbtIdentityDiffNode] = {}
    unique_id: str
    for unique_id in selected_unique_ids:
        node: DbtIdentityDiffNode = _build_diff_node(
            unique_id=unique_id,
            current_manifest=current_manifest,
            ref_manifest=ref_manifest,
            current_graph=current_graph,
            ref_graph=ref_graph,
            current_hashes=current_hashes,
            ref_hashes=ref_hashes,
            depth=depth,
            visited=frozenset(),
        )
        selected_nodes.append(node)
        _collect_causes(node=node, causes=causes_by_unique_id)
    return DbtIdentityDiffResult(
        selected=tuple(selected_nodes),
        causes=tuple(causes_by_unique_id.values()),
        against=against,
        warnings=(*current_manifest.seed_identity_warnings, *ref_manifest.seed_identity_warnings),
    )


def render_dbt_identity_diff_result(
    *, result: DbtIdentityDiffResult, quiet: bool, use_color: bool
) -> str:
    """Render a human-readable identity diff."""

    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [
        style.dbt_section("dbt identity diff") + f"  {style.muted('vs ' + result.against)}"
    ]
    lines.append("")
    node: DbtIdentityDiffNode
    for node in result.selected:
        _append_node(lines=lines, node=node, style=style, quiet=quiet, indent="")
        lines.append("")
    if result.causes:
        cause_labels: str = ", ".join(
            f"{cause.name} ({_reason_label(cause.local_diff.reasons)})"
            for cause in result.causes
            if cause.local_diff is not None
        )
        lines.append(style.warning_strong(f"=> {len(result.causes)} cause(s): ") + cause_labels)
    else:
        lines.append(style.success("=> no identity differences in selected models"))
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
        "selected": [_node_json(node) for node in result.selected],
        "causes": [node.unique_id for node in result.causes],
        "warnings": list(result.warnings),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _build_diff_node(
    *,
    unique_id: str,
    current_manifest: DbtManifestIndex,
    ref_manifest: DbtManifestIndex,
    current_graph: Mapping[str, tuple[str, ...]],
    ref_graph: Mapping[str, tuple[str, ...]],
    current_hashes: Mapping[str, str | None],
    ref_hashes: Mapping[str, str | None],
    depth: int | None,
    visited: frozenset[str],
) -> DbtIdentityDiffNode:
    current_hash: str | None = current_hashes.get(unique_id)
    ref_hash: str | None = ref_hashes.get(unique_id)
    name: str = _display_name(unique_id=unique_id, manifest=current_manifest) or _display_name(
        unique_id=unique_id,
        manifest=ref_manifest,
    )
    if current_hash == ref_hash and current_hash is not None:
        return DbtIdentityDiffNode(
            unique_id=unique_id,
            name=name,
            verdict=DbtIdentityDiffVerdict.WOULD_REUSE,
            current_version_hash=current_hash,
            ref_version_hash=ref_hash,
        )
    local_diff: DbtIdentityLocalDiff | None = _local_diff(
        unique_id=unique_id,
        current_manifest=current_manifest,
        ref_manifest=ref_manifest,
        current_graph=current_graph,
        ref_graph=ref_graph,
    )
    child_depth: int | None = None if depth is None else depth - 1
    children: tuple[DbtIdentityDiffNode, ...] = ()
    if unique_id not in visited and (depth is None or depth > 0):
        upstream_ids: tuple[str, ...] = _dedupe_sorted(
            (*current_graph.get(unique_id, ()), *ref_graph.get(unique_id, ()))
        )
        children = tuple(
            _build_diff_node(
                unique_id=upstream_id,
                current_manifest=current_manifest,
                ref_manifest=ref_manifest,
                current_graph=current_graph,
                ref_graph=ref_graph,
                current_hashes=current_hashes,
                ref_hashes=ref_hashes,
                depth=child_depth,
                visited=frozenset((*visited, unique_id)),
            )
            for upstream_id in upstream_ids
            if current_hashes.get(upstream_id) != ref_hashes.get(upstream_id)
        )
    verdict: DbtIdentityDiffVerdict = (
        DbtIdentityDiffVerdict.CAUSE
        if local_diff is not None and local_diff.reasons != (DbtIdentityDiffReason.UPSTREAM_ONLY,)
        else DbtIdentityDiffVerdict.UPSTREAM_ONLY
        if children
        else DbtIdentityDiffVerdict.REBUILD
    )
    if local_diff is None and children:
        local_diff = DbtIdentityLocalDiff(
            unique_id=unique_id,
            reasons=(DbtIdentityDiffReason.UPSTREAM_ONLY,),
        )
    return DbtIdentityDiffNode(
        unique_id=unique_id,
        name=name,
        verdict=verdict,
        current_version_hash=current_hash,
        ref_version_hash=ref_hash,
        local_diff=local_diff,
        children=children,
    )


def _local_diff(
    *,
    unique_id: str,
    current_manifest: DbtManifestIndex,
    ref_manifest: DbtManifestIndex,
    current_graph: Mapping[str, tuple[str, ...]],
    ref_graph: Mapping[str, tuple[str, ...]],
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
        sql_diff = tuple(format_query_diff(ref_sql, current_sql))
    elif _compiled_sql(ref_model) != _compiled_sql(current_model):
        reasons.append(DbtIdentityDiffReason.COMPILED_ONLY)
        sql_diff = tuple(format_query_diff(_compiled_sql(ref_model), _compiled_sql(current_model)))
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


def _own_hash(*, unique_id: str, manifest: DbtManifestIndex) -> str | None:
    seed: DbtManifestSeed | None = manifest.seeds_by_unique_id.get(unique_id)
    if seed is not None:
        return seed.identity_hash
    model: DbtManifestModel | None = manifest.models_by_unique_id.get(unique_id)
    if model is None:
        return None
    return model.node_checksum or hashlib.sha256(model.query_sql.encode("utf-8")).hexdigest()


def _append_node(
    *, lines: list[str], node: DbtIdentityDiffNode, style: CliStyle, quiet: bool, indent: str
) -> None:
    verdict: str = _styled_verdict(node.verdict, style=style)
    hashes: str = _hash_detail(node=node, style=style)
    lines.append(f"{indent}{style.dbt_object_name(node.name):<34} {verdict} {hashes}".rstrip())
    if node.local_diff is not None:
        reasons: str = _styled_reasons(node.local_diff.reasons, style=style)
        lines.append(f"{indent}  {style.muted('reason:')} {reasons}")
        if not quiet:
            _append_local_diff(lines=lines, diff=node.local_diff, style=style, indent=indent + "  ")
    child: DbtIdentityDiffNode
    for child in node.children:
        _append_node(lines=lines, node=child, style=style, quiet=quiet, indent=indent + "  └─ ")


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
        return style.warning("UPSTREAM only") + " " + style.muted("(own content same)")
    return ", ".join(
        style.warning_strong(reason.value.upper().replace("_", " ")) for reason in reasons
    )


def _hash_detail(*, node: DbtIdentityDiffNode, style: CliStyle) -> str:
    if node.current_version_hash is None or node.ref_version_hash is None:
        return style.muted("(missing identity)")
    if node.current_version_hash == node.ref_version_hash:
        return style.muted("(identity equal)")
    return style.muted("(identity differs)")


def _reason_label(reasons: tuple[DbtIdentityDiffReason, ...]) -> str:
    return "+".join(reason.value for reason in reasons)


def _node_json(node: DbtIdentityDiffNode) -> dict[str, object]:
    return {
        "unique_id": node.unique_id,
        "name": node.name,
        "verdict": node.verdict.value,
        "current_version_hash": node.current_version_hash,
        "ref_version_hash": node.ref_version_hash,
        "local_diff": None if node.local_diff is None else _local_diff_json(node.local_diff),
        "children": [_node_json(child) for child in node.children],
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


def _collect_causes(*, node: DbtIdentityDiffNode, causes: dict[str, DbtIdentityDiffNode]) -> None:
    if node.verdict == DbtIdentityDiffVerdict.CAUSE:
        causes.setdefault(node.unique_id, node)
    child: DbtIdentityDiffNode
    for child in node.children:
        _collect_causes(node=child, causes=causes)


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
