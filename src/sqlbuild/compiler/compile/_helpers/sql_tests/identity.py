"""Version identity for one expanded SQL test case."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledSqlTestResource
from sqlbuild.compiler.discovery.models import SqlTestParameterDeclaration
from sqlbuild.sql_values.main.identity import sql_value_identity
from sqlbuild.sql_values.models import SqlValue


def build_sql_test_case_fingerprint(
    *,
    source_path: Path,
    block_index: int,
    case_name: str,
    parameter_schema: tuple[SqlTestParameterDeclaration, ...],
    parameter_values: tuple[tuple[str, SqlValue], ...],
    expanded_sql: str,
    scope_deps: tuple[CompiledObjectKey, ...],
    tested_resources: tuple[CompiledSqlTestResource, ...],
) -> str:
    """Hash all compile-resolved inputs that version a stable test case."""

    payload: dict[str, object] = {
        "source_path": source_path.as_posix(),
        "block_index": block_index,
        "case_name": case_name,
        "parameter_schema": [
            (parameter.name, parameter.value_type.value, parameter.nullable)
            for parameter in parameter_schema
        ],
        "parameter_values": [
            (name, sql_value_identity(value=value)) for name, value in parameter_values
        ],
        "expanded_sql": expanded_sql,
        "scope_deps": sorted((str(dep.resource_type), dep.name) for dep in scope_deps),
        "tested_resources": sorted(
            (resource.kind.value, resource.name) for resource in tested_resources
        ),
    }
    encoded: str = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
