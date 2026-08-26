"""Macro node serialization for dbt-compatible manifest."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import LoadedMacro
from sqlbuild.compiler.discovery.models import DiscoveredSqlHookFile
from sqlbuild.compiler.manifest.constants import RESOURCE_TYPE_MACRO
from sqlbuild.compiler.scopes.models import DeclarationIdentity, DeclarationRecord, ScopeIndex
from sqlbuild.compiler.scopes.types import DeclarationKind


def build_macro_node(
    *,
    loaded_macro: LoadedMacro,
    project_name: str,
    dependencies: tuple[DeclarationIdentity, ...] = (),
    scope_record: DeclarationRecord | None = None,
) -> dict[str, object]:
    """Build one dbt-compatible macro node dict."""

    unique_id: str = f"macro.{project_name}.{loaded_macro.name}"

    return {
        "name": loaded_macro.name,
        "resource_type": RESOURCE_TYPE_MACRO,
        "package_name": project_name,
        "path": loaded_macro.relative_path.as_posix(),
        "original_file_path": loaded_macro.relative_path.as_posix(),
        "unique_id": unique_id,
        "macro_sql": loaded_macro.raw_source,
        "depends_on": {
            "macros": [f"macro.{project_name}.{dependency.name}" for dependency in dependencies]
        },
        "description": "",
        "meta": {
            "sqlbuild_visibility": (
                scope_record.scope.value if scope_record is not None else "global"
            ),
            "sqlbuild_scope_path": (scope_record.owning_path if scope_record is not None else None),
        },
        "docs": {"show": True, "node_color": None},
        "patch_path": None,
        "arguments": [],
        "created_at": 0.0,
        "supported_languages": None,
    }


def build_sql_hook_macro_node(
    *, hook_file: DiscoveredSqlHookFile, project_name: str
) -> dict[str, object]:
    """Expose one SQL hook definition through a dbt-compatible macro node."""

    hook_package_name: str = f"{project_name}__sqlbuild_hooks"
    return {
        "name": hook_file.name,
        "resource_type": RESOURCE_TYPE_MACRO,
        "package_name": hook_package_name,
        "path": hook_file.relative_path.as_posix(),
        "original_file_path": hook_file.relative_path.as_posix(),
        "unique_id": f"macro.{hook_package_name}.{hook_file.name}",
        "macro_sql": hook_file.sql_body,
        "depends_on": {"macros": []},
        "description": hook_file.description or "",
        "meta": {
            "sqlbuild_resource_type": "sql_hook",
            "sqlbuild_hook_name": hook_file.name,
        },
        "docs": {"show": True, "node_color": None},
        "patch_path": None,
        "arguments": [],
        "created_at": 0.0,
        "supported_languages": None,
    }


def build_manifest_macro_nodes(
    *,
    loaded_macros: dict[str, LoadedMacro],
    sql_hook_files: tuple[DiscoveredSqlHookFile, ...],
    project_name: str,
    scope_index: ScopeIndex | None = None,
) -> dict[str, dict[str, object]]:
    """Build all dbt-compatible macro entries, including SQL hook definitions."""

    macros: dict[str, dict[str, object]] = {}
    dependency_map: dict[str, tuple[DeclarationIdentity, ...]] = {
        record.identity.name: record.macro.dependencies
        for record in (() if scope_index is None else scope_index.declarations)
        if record.identity.kind is DeclarationKind.MACRO and record.macro is not None
    }
    scope_records: dict[str, DeclarationRecord] = {
        record.identity.name: record
        for record in (() if scope_index is None else scope_index.declarations)
        if record.identity.kind is DeclarationKind.MACRO
    }
    macro_name: str
    loaded_macro: LoadedMacro
    for macro_name, loaded_macro in loaded_macros.items():
        unique_id: str = f"macro.{project_name}.{macro_name}"
        macros[unique_id] = build_macro_node(
            loaded_macro=loaded_macro,
            project_name=project_name,
            dependencies=dependency_map.get(macro_name, ()),
            scope_record=scope_records.get(macro_name),
        )
    hook_file: DiscoveredSqlHookFile
    for hook_file in sql_hook_files:
        unique_id = f"macro.{project_name}__sqlbuild_hooks.{hook_file.name}"
        macros[unique_id] = build_sql_hook_macro_node(
            hook_file=hook_file,
            project_name=project_name,
        )
    return macros
