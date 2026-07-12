"""Shared helpers for column lineage extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.models import ColumnLineage, ColumnLineageSource
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)

_SQLBUILD_REF_PATTERN: re.Pattern[str] = re.compile(
    r"__(?P<kind>ref|source|seed)\(\s*(['\"])(?P<name>[^'\"]+)\2\s*\)"
)
_SQLBUILD_UDF_PATTERN: re.Pattern[str] = re.compile(
    r"__udf\(\s*(['\"])(?P<name>[^'\"]+)\1\s*\)\s*\("
)


@dataclass(frozen=True)
class _PhysicalResource:
    resource_type: CompiledResourceType
    resource_name: str
    physical_name: str


def _normalize_sqlbuild_refs(sql: str) -> tuple[str, tuple[_PhysicalResource, ...]]:
    def replace(match: re.Match[str]) -> str:
        kind: str = match.group("kind")
        name: str = match.group("name")
        resource_type: CompiledResourceType = {
            "ref": CompiledResourceType.MODEL,
            "source": CompiledResourceType.SOURCE,
            "seed": CompiledResourceType.SEED,
        }[kind]
        physical_name: str = _physical_resource_name(
            resource_type=resource_type, resource_name=name
        )
        return physical_name

    resources: tuple[_PhysicalResource, ...] = tuple(
        _PhysicalResource(
            resource_type={
                "ref": CompiledResourceType.MODEL,
                "source": CompiledResourceType.SOURCE,
                "seed": CompiledResourceType.SEED,
            }[match.group("kind")],
            resource_name=match.group("name"),
            physical_name=replace(match),
        )
        for match in _SQLBUILD_REF_PATTERN.finditer(sql)
    )
    normalized_sql: str = _SQLBUILD_REF_PATTERN.sub(replace, sql)
    normalized_sql = _SQLBUILD_UDF_PATTERN.sub(
        lambda match: f"{_physical_function_name(match.group('name'))}(",
        normalized_sql,
    )
    return normalized_sql, resources


def _physical_resource_name(*, resource_type: CompiledResourceType, resource_name: str) -> str:
    safe_name: str = re.sub(r"[^a-zA-Z0-9_]", "__", resource_name)
    return f"__sqlbuild_{resource_type.value}__{safe_name}"


def _physical_function_name(function_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "__", function_name)


def _build_schema_mapping(project: CompiledProject) -> dict[str, dict[str, str]]:
    schema: dict[str, dict[str, str]] = {}
    for model in project.models:
        columns: dict[str, str] = {}
        for column in model.inferred_columns or ():
            columns[column.name] = column.type or "UNKNOWN"
        for column in model.schema_entry.columns if model.schema_entry is not None else ():
            columns.setdefault(column.name, column.type or "UNKNOWN")
        if columns:
            schema[
                _physical_resource_name(
                    resource_type=CompiledResourceType.MODEL, resource_name=model.name
                )
            ] = columns
    for source in project.sources:
        columns: dict[str, str] = {
            column.name: column.type or "UNKNOWN" for column in source.source_entry.columns
        }
        if columns:
            schema[
                _physical_resource_name(
                    resource_type=CompiledResourceType.SOURCE, resource_name=source.name
                )
            ] = columns
    for seed in project.seeds:
        columns: dict[str, str] = {
            column.name: column.type or "UNKNOWN" for column in seed.schema_entry.columns
        }
        if columns:
            schema[
                _physical_resource_name(
                    resource_type=CompiledResourceType.SEED, resource_name=seed.name
                )
            ] = columns
    return schema


def _build_star_lineage(
    *,
    model: CompiledModel,
    schema: dict[str, dict[str, str]],
    physical_resources: tuple[_PhysicalResource, ...],
    existing_columns: set[str],
) -> tuple[ColumnLineage, ...]:
    lineages: list[ColumnLineage] = []
    seen_columns: set[str] = set(existing_columns)
    for resource in physical_resources:
        for column_name in schema.get(resource.physical_name, {}):
            if column_name in seen_columns:
                continue
            seen_columns.add(column_name)
            lineages.append(
                ColumnLineage(
                    output_column=column_name,
                    transform_kind=ColumnTransformKind.STAR,
                    expression_sql=None,
                    upstream_columns=(
                        ColumnLineageSource(
                            resource_type=resource.resource_type,
                            resource_name=resource.resource_name,
                            column_name=column_name,
                        ),
                    ),
                    nullability=InferredNullability.UNKNOWN,
                    confidence=ColumnLineageConfidence.MEDIUM,
                )
            )
    return tuple(lineages)
