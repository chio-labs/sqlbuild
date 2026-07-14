"""Macro node serialization for dbt-compatible manifest."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import LoadedMacro
from sqlbuild.compiler.manifest.constants import RESOURCE_TYPE_MACRO


def build_macro_node(
    *,
    loaded_macro: LoadedMacro,
    project_name: str,
) -> dict[str, object]:
    """Build one dbt-compatible macro node dict."""

    unique_id: str = f"macro.{project_name}.{loaded_macro.name}"

    return {
        "name": loaded_macro.name,
        "resource_type": RESOURCE_TYPE_MACRO,
        "package_name": project_name,
        "path": str(loaded_macro.relative_path),
        "original_file_path": str(loaded_macro.relative_path),
        "unique_id": unique_id,
        "macro_sql": loaded_macro.raw_source,
        "depends_on": {"macros": []},
        "description": "",
        "meta": {},
        "docs": {"show": True, "node_color": None},
        "patch_path": None,
        "arguments": [],
        "created_at": 0.0,
        "supported_languages": None,
    }
