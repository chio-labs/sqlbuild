"""dbt manifest loading and model lookup helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSource,
)
from sqlbuild.shared.types import SqlReferenceKind

_INDEXED_NODE_RESOURCE_TYPES: frozenset[str] = frozenset({"model", "snapshot"})


def load_dbt_manifest_index(*, manifest_path: Path) -> DbtManifestIndex:
    """Load and index dbt model nodes from a manifest.json file."""

    if not manifest_path.is_file():
        raise CompileInputError(
            f"dbt manifest file does not exist: {manifest_path}",
            code="C210",
            help="Run dbt compile or configure dbt target_path so SQLBuild can read manifest.json.",
        )
    try:
        raw_data: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CompileInputError(
            f"Invalid dbt manifest JSON: {exc.msg}",
            code="C211",
        ) from exc
    return build_dbt_manifest_index(raw_data=raw_data)


def build_dbt_manifest_index(*, raw_data: object) -> DbtManifestIndex:
    """Build dbt model lookup indexes from decoded manifest JSON."""

    if not isinstance(raw_data, dict):
        raise CompileInputError("Invalid dbt manifest: root must be an object", code="C211")
    manifest_data: dict[str, object] = cast(dict[str, object], raw_data)
    raw_nodes: object | None = manifest_data.get("nodes")
    if not isinstance(raw_nodes, dict):
        raise CompileInputError("Invalid dbt manifest: nodes must be an object", code="C211")
    raw_sources: object | None = manifest_data.get("sources")
    if raw_sources is None:
        raw_sources = {}
    if not isinstance(raw_sources, dict):
        raise CompileInputError("Invalid dbt manifest: sources must be an object", code="C211")

    models_by_unique_id: dict[str, DbtManifestModel] = {}
    models_by_name_lists: dict[str, list[DbtManifestModel]] = {}
    models_by_package_and_name: dict[tuple[str, str], DbtManifestModel] = {}
    sources_by_unique_id: dict[str, DbtManifestSource] = {}
    unique_id: object
    raw_node: object
    for unique_id, raw_node in raw_nodes.items():
        if not isinstance(unique_id, str) or not isinstance(raw_node, dict):
            continue
        node_data: dict[object, object] = cast(dict[object, object], raw_node)
        if node_data.get("resource_type") not in _INDEXED_NODE_RESOURCE_TYPES:
            continue
        model: DbtManifestModel = _parse_model(unique_id=unique_id, raw_node=node_data)
        models_by_unique_id[model.unique_id] = model
        models_by_name_lists.setdefault(model.name, []).append(model)
        models_by_package_and_name[(model.package_name, model.name)] = model

    for unique_id, raw_node in raw_sources.items():
        if not isinstance(unique_id, str) or not isinstance(raw_node, dict):
            continue
        node_data = cast(dict[object, object], raw_node)
        if node_data.get("resource_type") != "source":
            continue
        source: DbtManifestSource = _parse_source(unique_id=unique_id, raw_node=node_data)
        sources_by_unique_id[source.unique_id] = source

    return DbtManifestIndex(
        models_by_unique_id=models_by_unique_id,
        models_by_name={name: tuple(models) for name, models in models_by_name_lists.items()},
        models_by_package_and_name=models_by_package_and_name,
        sources_by_unique_id=sources_by_unique_id,
    )


def resolve_dbt_manifest_model(
    *, manifest: DbtManifestIndex, name: str, package_name: str | None = None
) -> DbtManifestModel:
    """Resolve a dbt model by one-arg or package-qualified ref semantics."""

    if package_name is not None:
        model: DbtManifestModel | None = manifest.models_by_package_and_name.get(
            (package_name, name)
        )
        if model is None:
            raise CompileInputError(
                f"dbt model '{package_name}.{name}' was not found in manifest",
                code="C212",
                help=(
                    f"Check the {SqlReferenceKind.DBT_REF.placeholder_call('...')} package/name "
                    "or run dbt compile to refresh manifest.json."
                ),
            )
        return model

    matches: tuple[DbtManifestModel, ...] = manifest.models_by_name.get(name, ())
    if not matches:
        raise CompileInputError(
            f"dbt model '{name}' was not found in manifest",
            code="C212",
            help=(
                f"Check the {SqlReferenceKind.DBT_REF.placeholder_call('...')} name or run dbt "
                "compile to refresh manifest.json."
            ),
        )
    if len(matches) > 1:
        packages: str = ", ".join(sorted(model.package_name for model in matches))
        raise CompileInputError(
            f"dbt model '{name}' is ambiguous across packages: {packages}",
            code="C213",
            help=(
                f"Use {SqlReferenceKind.DBT_REF.example_call('package_name', name)} to "
                "choose one dbt model."
            ),
        )
    return matches[0]


def _parse_model(*, unique_id: str, raw_node: dict[object, object]) -> DbtManifestModel:
    package_name: str = _required_str(raw_node.get("package_name"), field_name="package_name")
    name: str = _required_str(raw_node.get("name"), field_name="name")
    database: str | None = _optional_str(raw_node.get("database"))
    schema: str | None = _optional_str(raw_node.get("schema"))
    alias: str | None = _optional_str(raw_node.get("alias"))
    relation_name: str | None = _optional_str(raw_node.get("relation_name"))
    if relation_name is None:
        relation_name = _render_relation_name(database=database, schema=schema, name=alias or name)
    depends_on_nodes: tuple[str, ...] = _parse_depends_on_nodes(raw_node.get("depends_on"))
    return DbtManifestModel(
        unique_id=unique_id,
        package_name=package_name,
        name=name,
        database=database,
        schema=schema,
        alias=alias,
        node_checksum=_parse_checksum(raw_node.get("checksum")),
        relation_name=relation_name,
        fqn=_parse_fqn(raw_node.get("fqn")),
        query_sql=_model_query_sql(raw_node=raw_node),
        depends_on_nodes=depends_on_nodes,
        payload={str(key): value for key, value in raw_node.items()},
    )


def _parse_source(*, unique_id: str, raw_node: dict[object, object]) -> DbtManifestSource:
    package_name: str = _required_str(raw_node.get("package_name"), field_name="package_name")
    source_name: str = _required_str(raw_node.get("source_name"), field_name="source_name")
    name: str = _required_str(raw_node.get("name"), field_name="name")
    database: str | None = _optional_str(raw_node.get("database"))
    schema: str | None = _optional_str(raw_node.get("schema"))
    identifier: str | None = _optional_str(raw_node.get("identifier"))
    relation_name: str | None = _optional_str(raw_node.get("relation_name"))
    if relation_name is None:
        relation_name = _render_relation_name(
            database=database,
            schema=schema,
            name=identifier or name,
        )
    freshness: dict[str, object] | None = _optional_dict(raw_node.get("freshness"))
    return DbtManifestSource(
        unique_id=unique_id,
        package_name=package_name,
        source_name=source_name,
        name=name,
        database=database,
        schema=schema,
        identifier=identifier,
        relation_name=relation_name,
        loaded_at_field=_optional_str(raw_node.get("loaded_at_field")),
        loaded_at_query=_optional_str(raw_node.get("loaded_at_query")),
        freshness=freshness,
        freshness_filter=_source_freshness_filter(raw_node=raw_node, freshness=freshness),
        payload={str(key): value for key, value in raw_node.items()},
    )


def _source_freshness_filter(
    *, raw_node: dict[object, object], freshness: dict[str, object] | None
) -> str | None:
    filter_value: str | None = _optional_str(raw_node.get("filter"))
    if filter_value is not None:
        return filter_value
    if freshness is None:
        return None
    return _optional_str(freshness.get("filter"))


def _render_relation_name(*, database: str | None, schema: str | None, name: str) -> str:
    parts: tuple[str, ...] = tuple(part for part in (database, schema, name) if part)
    return ".".join(parts)


def _model_query_sql(*, raw_node: dict[object, object]) -> str:
    return (
        _optional_str(raw_node.get("raw_code"))
        or _optional_str(raw_node.get("compiled_code"))
        or _optional_str(raw_node.get("raw_sql"))
        or _optional_str(raw_node.get("compiled_sql"))
        or ""
    )


def _required_str(value: object, *, field_name: str) -> str:
    if isinstance(value, str) and value:
        return value
    raise CompileInputError(f"Invalid dbt manifest: model {field_name} is required", code="C211")


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _optional_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    return None


def _parse_fqn(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    parts: list[str] = []
    item: object
    for item in value:
        if not isinstance(item, str) or not item:
            return ()
        parts.append(item)
    return tuple(parts)


def _parse_checksum(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if not isinstance(value, dict):
        return None
    raw_checksum: dict[str, object] = cast(dict[str, object], value)
    checksum: object | None = raw_checksum.get("checksum")
    return checksum if isinstance(checksum, str) and checksum else None


def _parse_depends_on_nodes(value: object) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    depends_on: dict[str, object] = cast(dict[str, object], value)
    raw_nodes: object | None = depends_on.get("nodes")
    if not isinstance(raw_nodes, list):
        return ()
    return tuple(node for node in raw_nodes if isinstance(node, str) and node)
