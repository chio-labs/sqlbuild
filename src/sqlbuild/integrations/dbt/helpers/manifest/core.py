"""dbt manifest loading and model lookup helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.integrations.dbt.constants import (
    DBT_DEFINITION_FINGERPRINT_EXCLUDED_CONFIG_KEYS,
    DBT_MANIFEST_CONFIG_KEY,
)
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSeed,
    DbtManifestSource,
)
from sqlbuild.integrations.dbt.types import DbtSupportedResourceType
from sqlbuild.shared.types import SqlReferenceKind

_INDEXED_NODE_RESOURCE_TYPES: frozenset[DbtSupportedResourceType] = frozenset(
    {DbtSupportedResourceType.MODEL, DbtSupportedResourceType.SNAPSHOT}
)
_DBT_RAW_CODE_KEYS: tuple[str, ...] = ("raw_code", "raw_sql")
_DBT_DEPENDS_ON_KEY: str = "depends_on"
_DBT_DEPENDS_ON_MACROS_KEY: str = "macros"
_DBT_MACRO_SQL_KEY: str = "macro_sql"
_DBT_USER_MACRO_PREFIX: str = "macro."
_SQLBUILD_SEED_CONTENT_HASH_KEY: str = "sqlbuild_seed_content_hash"


@dataclass(frozen=True)
class _MacroIndex:
    macro_sql_by_id: dict[str, str]
    macro_deps_by_id: dict[str, tuple[str, ...]]


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

    macro_index: _MacroIndex = _build_macro_index(raw_macros=manifest_data.get("macros"))
    models_by_unique_id: dict[str, DbtManifestModel] = {}
    models_by_name_lists: dict[str, list[DbtManifestModel]] = {}
    models_by_package_and_name: dict[tuple[str, str], DbtManifestModel] = {}
    sources_by_unique_id: dict[str, DbtManifestSource] = {}
    seeds_by_unique_id: dict[str, DbtManifestSeed] = {}
    seed_identity_warnings: list[str] = []
    unique_id: object
    raw_node: object
    for unique_id, raw_node in raw_nodes.items():
        if not isinstance(unique_id, str) or not isinstance(raw_node, dict):
            continue
        node_data: dict[object, object] = cast(dict[object, object], raw_node)
        resource_type: object = node_data.get("resource_type")
        if resource_type in _INDEXED_NODE_RESOURCE_TYPES:
            model: DbtManifestModel = _parse_model(
                unique_id=unique_id, raw_node=node_data, macro_index=macro_index
            )
            models_by_unique_id[model.unique_id] = model
            models_by_name_lists.setdefault(model.name, []).append(model)
            models_by_package_and_name[(model.package_name, model.name)] = model
            continue
        if resource_type == DbtSupportedResourceType.SEED:
            seed: DbtManifestSeed = _parse_seed(
                unique_id=unique_id, raw_node=node_data, warnings=seed_identity_warnings
            )
            seeds_by_unique_id[seed.unique_id] = seed

    for unique_id, raw_node in raw_sources.items():
        if not isinstance(unique_id, str) or not isinstance(raw_node, dict):
            continue
        node_data = cast(dict[object, object], raw_node)
        if node_data.get("resource_type") != DbtSupportedResourceType.SOURCE:
            continue
        source: DbtManifestSource = _parse_source(unique_id=unique_id, raw_node=node_data)
        sources_by_unique_id[source.unique_id] = source

    return DbtManifestIndex(
        models_by_unique_id=models_by_unique_id,
        models_by_name={name: tuple(models) for name, models in models_by_name_lists.items()},
        models_by_package_and_name=models_by_package_and_name,
        sources_by_unique_id=sources_by_unique_id,
        seeds_by_unique_id=seeds_by_unique_id,
        seed_identity_warnings=tuple(seed_identity_warnings),
    )


def precompute_dbt_manifest_seed_content_hashes(*, raw_data: object) -> object:
    """Return manifest JSON data with seed content hashes embedded while files exist."""

    if not isinstance(raw_data, dict):
        return raw_data
    manifest_data: dict[str, object] = cast(dict[str, object], raw_data)
    raw_nodes: object | None = manifest_data.get("nodes")
    if not isinstance(raw_nodes, dict):
        return raw_data
    raw_node: object
    for raw_node in raw_nodes.values():
        if not isinstance(raw_node, dict):
            continue
        node_data: dict[object, object] = cast(dict[object, object], raw_node)
        if node_data.get("resource_type") != DbtSupportedResourceType.SEED:
            continue
        content_hash: str | None = _read_seed_content_hash(raw_node=node_data)
        if content_hash is not None:
            node_data[_SQLBUILD_SEED_CONTENT_HASH_KEY] = content_hash
    return raw_data


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


def _parse_model(
    *, unique_id: str, raw_node: dict[object, object], macro_index: _MacroIndex
) -> DbtManifestModel:
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
        definition_fingerprint=_model_definition_fingerprint(
            raw_node=raw_node, macro_index=macro_index
        ),
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


def _parse_seed(
    *, unique_id: str, raw_node: dict[object, object], warnings: list[str]
) -> DbtManifestSeed:
    package_name: str = _required_str(raw_node.get("package_name"), field_name="package_name")
    name: str = _required_str(raw_node.get("name"), field_name="name")
    database: str | None = _optional_str(raw_node.get("database"))
    schema: str | None = _optional_str(raw_node.get("schema"))
    alias: str | None = _optional_str(raw_node.get("alias"))
    relation_name: str | None = _optional_str(raw_node.get("relation_name"))
    if relation_name is None:
        relation_name = _render_relation_name(database=database, schema=schema, name=alias or name)
    return DbtManifestSeed(
        unique_id=unique_id,
        package_name=package_name,
        name=name,
        database=database,
        schema=schema,
        alias=alias,
        relation_name=relation_name,
        identity_hash=_seed_identity_hash(
            unique_id=unique_id, raw_node=raw_node, warnings=warnings
        ),
        payload={str(key): value for key, value in raw_node.items()},
    )


def _seed_identity_hash(
    *, unique_id: str, raw_node: dict[object, object], warnings: list[str]
) -> str | None:
    checksum: str | None = _parse_checksum(raw_node.get("checksum"))
    config: object = raw_node.get(DBT_MANIFEST_CONFIG_KEY)
    config_mapping: dict[str, object] = (
        cast(dict[str, object], config) if isinstance(config, dict) else {}
    )
    identity: dict[str, object] = {
        "checksum": checksum,
        "config": _normalize_json_value(config_mapping),
        "content": _seed_content_hash(unique_id=unique_id, raw_node=raw_node, warnings=warnings),
    }
    payload: str = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _seed_content_hash(
    *, unique_id: str, raw_node: dict[object, object], warnings: list[str]
) -> str | None:
    precomputed: str | None = _optional_str(raw_node.get(_SQLBUILD_SEED_CONTENT_HASH_KEY))
    if precomputed is not None:
        return precomputed
    content_hash: str | None = _read_seed_content_hash(raw_node=raw_node)
    if content_hash is not None:
        return content_hash
    root_path: str | None = _optional_str(raw_node.get("root_path"))
    relative_path: str | None = _optional_str(raw_node.get("original_file_path"))
    if root_path is None or relative_path is None:
        warnings.append(
            f"seed '{unique_id}': missing manifest path; independent content change "
            "detection is inactive (relying on dbt checksum only)"
        )
        return None
    seed_file: Path = Path(root_path) / relative_path
    try:
        seed_file.read_text(encoding="utf-8-sig")
    except (OSError, ValueError) as exc:
        warnings.append(
            f"seed '{unique_id}': could not read seed file ({exc}); independent content "
            "change detection is inactive (relying on dbt checksum only)"
        )
    return None


def _read_seed_content_hash(*, raw_node: dict[object, object]) -> str | None:
    root_path: str | None = _optional_str(raw_node.get("root_path"))
    relative_path: str | None = _optional_str(raw_node.get("original_file_path"))
    if root_path is None or relative_path is None:
        return None
    seed_file: Path = Path(root_path) / relative_path
    try:
        text: str = seed_file.read_text(encoding="utf-8-sig")
    except (OSError, ValueError):
        return None
    normalized: str = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_json_value(value: object) -> object:
    if isinstance(value, dict):
        mapping: dict[object, object] = cast(dict[object, object], value)
        return {str(k): _normalize_json_value(mapping[k]) for k in sorted(mapping, key=str)}
    if isinstance(value, list):
        items: list[object] = cast(list[object], value)
        return [_normalize_json_value(item) for item in items]
    return value


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


def _build_macro_index(*, raw_macros: object) -> _MacroIndex:
    macro_sql_by_id: dict[str, str] = {}
    macro_deps_by_id: dict[str, tuple[str, ...]] = {}
    if not isinstance(raw_macros, dict):
        return _MacroIndex(macro_sql_by_id={}, macro_deps_by_id={})
    macros: dict[object, object] = cast(dict[object, object], raw_macros)
    macro_id: object
    macro_node: object
    for macro_id, macro_node in macros.items():
        if not isinstance(macro_id, str) or not isinstance(macro_node, dict):
            continue
        node: dict[object, object] = cast(dict[object, object], macro_node)
        macro_sql_by_id[macro_id] = _optional_str(node.get(_DBT_MACRO_SQL_KEY)) or ""
        macro_deps_by_id[macro_id] = _parse_macro_dependencies(node.get(_DBT_DEPENDS_ON_KEY))
    return _MacroIndex(macro_sql_by_id=macro_sql_by_id, macro_deps_by_id=macro_deps_by_id)


def _parse_macro_dependencies(value: object) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    depends_on: dict[object, object] = cast(dict[object, object], value)
    raw_macros: object | None = depends_on.get(_DBT_DEPENDS_ON_MACROS_KEY)
    if not isinstance(raw_macros, list):
        return ()
    return tuple(macro for macro in raw_macros if isinstance(macro, str) and macro)


def _transitive_macro_ids(
    *, direct_macro_ids: tuple[str, ...], macro_index: _MacroIndex
) -> set[str]:
    resolved: set[str] = set()
    pending: list[str] = list(direct_macro_ids)
    while pending:
        macro_id: str = pending.pop()
        if macro_id in resolved:
            continue
        resolved.add(macro_id)
        pending.extend(macro_index.macro_deps_by_id.get(macro_id, ()))
    return resolved


def _strip_config_block(raw_code: str) -> str:
    """Return raw_code with leading config blocks and snapshot wrappers removed.

    Snapshot env placement (target_schema) lives in the config() block, so the
    config text is dropped here; structured config is fingerprinted separately.
    """

    body: str = raw_code
    if _find_jinja_statement(body, "snapshot") is not None:
        body = _remove_jinja_statement(body, "snapshot")
        body = _remove_jinja_statement(body, "endsnapshot")
    body = _remove_config_call(body)
    return body.strip()


def _find_jinja_statement(text: str, keyword: str) -> int | None:
    marker: str = "{%"
    index: int = 0
    while True:
        start: int = text.find(marker, index)
        if start == -1:
            return None
        end: int = text.find("%}", start)
        if end == -1:
            return None
        if text[start + len(marker) : end].strip().split(" ")[0] == keyword:
            return start
        index = end + 2


def _remove_jinja_statement(text: str, keyword: str) -> str:
    start: int | None = _find_jinja_statement(text, keyword)
    if start is None:
        return text
    end: int = text.find("%}", start)
    return text[:start] + text[end + 2 :]


def _remove_config_call(text: str) -> str:
    marker: str = "{{"
    index: int = 0
    while True:
        start: int = text.find(marker, index)
        if start == -1:
            return text
        inner_start: int = start + len(marker)
        call_index: int = _skip_whitespace(text, inner_start)
        if text[call_index:].startswith("config"):
            close: int = text.find("}}", start)
            if close == -1:
                return text
            return text[:start] + text[close + 2 :]
        index = start + len(marker)


def _skip_whitespace(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _model_definition_fingerprint(
    *, raw_node: dict[object, object], macro_index: _MacroIndex
) -> str:
    raw_code: str = ""
    for key in _DBT_RAW_CODE_KEYS:
        raw_code = _optional_str(raw_node.get(key)) or raw_code
        if raw_code:
            break
    body: str = _strip_config_block(raw_code)
    config: object | None = raw_node.get(DBT_MANIFEST_CONFIG_KEY)
    config_mapping: dict[object, object] = (
        cast(dict[object, object], config) if isinstance(config, dict) else {}
    )
    config_parts: list[str] = [
        f"{key}={json.dumps(value, sort_keys=True, default=str)}"
        for key, value in sorted(config_mapping.items(), key=lambda item: str(item[0]))
        if str(key) not in DBT_DEFINITION_FINGERPRINT_EXCLUDED_CONFIG_KEYS
    ]
    direct_macro_ids: tuple[str, ...] = _parse_macro_dependencies(raw_node.get(_DBT_DEPENDS_ON_KEY))
    macro_ids: set[str] = _transitive_macro_ids(
        direct_macro_ids=direct_macro_ids, macro_index=macro_index
    )
    macro_parts: list[str] = [
        hashlib.sha256(macro_index.macro_sql_by_id.get(macro_id, "").encode("utf-8")).hexdigest()
        for macro_id in sorted(macro_ids)
        if macro_id.startswith(_DBT_USER_MACRO_PREFIX)
    ]
    return "\n".join((body, *config_parts, *macro_parts))


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
