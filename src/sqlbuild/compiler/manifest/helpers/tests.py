"""Test node serialization for dbt-compatible manifest.

Maps SQLBuild audits to dbt GenericTest nodes and SQL-native tests to SingularTest nodes.
"""

from __future__ import annotations

from sqlbuild.compiler.manifest.constants import CHECKSUM_HASH_NAME, RESOURCE_TYPE_TEST
from sqlbuild.compiler.manifest.helpers.shared import _key_to_unique_id
from sqlbuild.compiler.planner.models import AuditPlanEntry, ChainStep, SqlTestPlanEntry

_TEST_CONFIG: dict[str, object] = {
    "enabled": True,
    "alias": None,
    "schema": None,
    "database": None,
    "tags": [],
    "meta": {},
    "group": None,
    "materialized": "test",
    "severity": "ERROR",
    "store_failures": None,
    "store_failures_as": None,
    "where": None,
    "limit": None,
    "fail_calc": "count(*)",
    "warn_if": "!= 0",
    "error_if": "!= 0",
}


def build_audit_test_nodes(
    *,
    audit_entry: AuditPlanEntry,
    project_name: str,
) -> dict[str, dict[str, object]]:
    """Build dbt-compatible GenericTest nodes from one audit plan entry."""

    unique_id: str = f"test.{project_name}.{audit_entry.name}"
    compiled_code: str = audit_entry.resolved_sql

    test_metadata: dict[str, object] = {"name": audit_entry.name}
    kwargs: dict[str, object] = {}
    if audit_entry.attached_target_name is not None:
        kwargs["model"] = audit_entry.attached_target_name
    if audit_entry.attached_column_name is not None:
        kwargs["column_name"] = audit_entry.attached_column_name
    test_metadata["kwargs"] = kwargs

    depends_on_nodes: list[str] = [
        _key_to_unique_id(dep, project_name) for dep in audit_entry.scope_deps
    ]

    node: dict[str, object] = {
        "database": None,
        "schema": "",
        "name": audit_entry.name,
        "resource_type": RESOURCE_TYPE_TEST,
        "package_name": project_name,
        "path": "",
        "original_file_path": "",
        "unique_id": unique_id,
        "fqn": [project_name, audit_entry.name],
        "alias": audit_entry.name,
        "checksum": {"name": CHECKSUM_HASH_NAME, "checksum": ""},
        "config": dict(_TEST_CONFIG),
        "tags": [],
        "description": "",
        "columns": {},
        "meta": {"sqlbuild_test_type": "audit"},
        "group": None,
        "docs": {"show": True, "node_color": None},
        "patch_path": None,
        "build_path": None,
        "unrendered_config": {},
        "created_at": 0.0,
        "config_call_dict": {},
        "unrendered_config_call_dict": {},
        "relation_name": None,
        "raw_code": compiled_code,
        "compiled_code": compiled_code,
        "depends_on": {"macros": [], "nodes": depends_on_nodes},
        "test_metadata": test_metadata,
        "column_name": audit_entry.attached_column_name,
    }
    return {unique_id: node}


def build_sql_test_nodes(
    *,
    test_entry: SqlTestPlanEntry,
    project_name: str,
) -> dict[str, dict[str, object]]:
    """Build dbt-compatible SingularTest nodes from one SQL test plan entry."""

    unique_id: str = f"test.{project_name}.{test_entry.name}"

    compiled_parts: list[str] = []
    step: ChainStep
    for step in test_entry.chain:
        compiled_parts.append(f"-- step: {step.model_name}")
        compiled_parts.append(step.resolved_sql)
    compiled_code: str = "\n\n".join(compiled_parts)

    depends_on_nodes: list[str] = [
        _key_to_unique_id(dep, project_name) for dep in test_entry.scope_deps
    ]

    node: dict[str, object] = {
        "database": None,
        "schema": "",
        "name": test_entry.name,
        "resource_type": RESOURCE_TYPE_TEST,
        "package_name": project_name,
        "path": "",
        "original_file_path": "",
        "unique_id": unique_id,
        "fqn": [project_name, test_entry.name],
        "alias": test_entry.name,
        "checksum": {"name": CHECKSUM_HASH_NAME, "checksum": ""},
        "config": dict(_TEST_CONFIG),
        "tags": [],
        "description": "",
        "columns": {},
        "meta": {"sqlbuild_test_type": "sql_native"},
        "group": None,
        "docs": {"show": True, "node_color": None},
        "patch_path": None,
        "build_path": None,
        "unrendered_config": {},
        "created_at": 0.0,
        "config_call_dict": {},
        "unrendered_config_call_dict": {},
        "relation_name": None,
        "raw_code": compiled_code,
        "compiled_code": compiled_code,
        "depends_on": {"macros": [], "nodes": depends_on_nodes},
    }
    return {unique_id: node}
