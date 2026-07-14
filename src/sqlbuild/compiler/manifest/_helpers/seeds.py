"""Seed node serialization for dbt-compatible manifest."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledSeed
from sqlbuild.compiler.manifest._helpers.shared import build_columns_dict, build_fqn
from sqlbuild.compiler.manifest.constants import CHECKSUM_HASH_NAME, RESOURCE_TYPE_SEED


def build_seed_node(
    *,
    seed: CompiledSeed,
    project_name: str,
) -> dict[str, object]:
    """Build one dbt-compatible seed node dict."""

    unique_id: str = f"seed.{project_name}.{seed.name}"
    relative_path_str: str = str(seed.seed_file.relative_path)

    return {
        "database": seed.destination.database,
        "schema": seed.destination.schema,
        "name": seed.name,
        "resource_type": RESOURCE_TYPE_SEED,
        "package_name": project_name,
        "path": relative_path_str,
        "original_file_path": relative_path_str,
        "unique_id": unique_id,
        "fqn": build_fqn(
            project_name=project_name,
            relative_path=seed.seed_file.relative_path,
        ),
        "alias": seed.destination.name,
        "checksum": {
            "name": CHECKSUM_HASH_NAME,
            "checksum": "",
        },
        "config": {
            "enabled": True,
            "alias": None,
            "schema": seed.destination.schema,
            "database": seed.destination.database,
            "tags": [],
            "meta": {},
            "group": None,
            "materialized": "seed",
            "persist_docs": {},
            "post-hook": [],
            "pre-hook": [],
            "quoting": {},
            "column_types": {},
            "full_refresh": None,
            "unique_key": None,
            "on_schema_change": "ignore",
            "on_configuration_change": "apply",
            "grants": {},
            "packages": [],
            "docs": {"show": True, "node_color": None},
            "contract": {"enforced": False, "alias_types": True},
            "delimiter": ",",
            "quote_columns": None,
        },
        "tags": [],
        "description": seed.schema_entry.description or "",
        "columns": build_columns_dict(seed.schema_entry),
        "meta": dict(seed.schema_entry.meta) if seed.schema_entry.meta else {},
        "group": None,
        "docs": {"show": True, "node_color": None},
        "patch_path": None,
        "build_path": None,
        "unrendered_config": {},
        "created_at": 0.0,
        "config_call_dict": {},
        "unrendered_config_call_dict": {},
        "relation_name": seed.destination.qualified_name,
        "raw_code": "",
        "root_path": None,
        "depends_on": {"macros": []},
    }
