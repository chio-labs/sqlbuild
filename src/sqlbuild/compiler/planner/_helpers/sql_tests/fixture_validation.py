"""Static SQL-test fixture shape validation."""

from __future__ import annotations

import re

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main._infer_fixture_columns import infer_fixture_columns
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledSqlTest,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import ColumnTransformKind
from sqlbuild.compiler.planner.exceptions import SqlTestFixtureValidationError

_COLLECTION_TYPES: frozenset[str] = frozenset(
    {"ARRAY", "LIST", "MAP", "OBJECT", "STRUCT", "VARIANT"}
)


def validate_test_fixtures(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    adapter: BaseAdapter,
    ordered_model_names: tuple[str, ...],
    mock_refs: dict[str, str],
    mock_sources: dict[str, str],
    mock_seeds: dict[str, str],
    expected_outputs: dict[str, str],
) -> None:
    """Report all statically provable missing columns and collection-type mismatches."""

    model_map: dict[str, CompiledModel] = {model.name: model for model in project.models}
    inferred_by_fixture: dict[tuple[CompiledResourceType, str], tuple[InferredColumn, ...]] = {}
    fixture_groups: tuple[tuple[CompiledResourceType, dict[str, str]], ...] = (
        (CompiledResourceType.MODEL, mock_refs),
        (CompiledResourceType.SOURCE, mock_sources),
        (CompiledResourceType.SEED, mock_seeds),
    )
    for resource_type, fixtures in fixture_groups:
        for name, sql in fixtures.items():
            inferred: tuple[InferredColumn, ...] | None = infer_fixture_columns(
                query_sql=sql,
                inference_profile=adapter.expression_inference_profile(),
            )
            if inferred is not None:
                inferred_by_fixture[(resource_type, name)] = inferred

    required: dict[tuple[CompiledResourceType, str], dict[str, set[str]]] = {}
    for model_name in ordered_model_names:
        model: CompiledModel | None = model_map.get(model_name)
        if model is None:
            continue
        for lineage_column in model.fast_lineage_columns or ():
            for upstream in lineage_column.upstream_columns:
                key: tuple[CompiledResourceType, str] = (
                    CompiledResourceType(upstream.resource_type),
                    upstream.resource_name,
                )
                if key not in inferred_by_fixture:
                    continue
                required.setdefault(key, {}).setdefault(upstream.column_name, set()).add(model_name)

    errors: list[str] = []
    for key, required_columns in sorted(
        required.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        available: dict[str, InferredColumn] = {
            column.name.casefold(): column for column in inferred_by_fixture[key]
        }
        missing: tuple[str, ...] = tuple(
            sorted(name for name in required_columns if name.casefold() not in available)
        )
        if missing:
            model_names: set[str] = set()
            for name in missing:
                model_names.update(required_columns[name])
            models: tuple[str, ...] = tuple(sorted(model_names))
            errors.append(
                f"{_fixture_location(test=test, resource_type=key[0], name=key[1])}: "
                f"mock {key[0].value} '{key[1]}' is missing required columns: "
                f"{', '.join(missing)} (read by: {', '.join(models)})"
            )

    expected_types: dict[tuple[CompiledResourceType, str], dict[str, str]] = {}
    for model_name, model in model_map.items():
        columns: tuple[InferredColumn, ...] = model.inferred_columns or ()
        expected_types[(CompiledResourceType.MODEL, model_name)] = {
            column.name.casefold(): column.type for column in columns if column.type is not None
        }
        if model.schema_entry is not None:
            expected_types[(CompiledResourceType.MODEL, model_name)].update(
                {
                    column.name.casefold(): column.type
                    for column in model.schema_entry.columns
                    if column.type is not None
                }
            )
    for source in project.sources:
        expected_types[(CompiledResourceType.SOURCE, source.name)] = {
            column.name.casefold(): column.type
            for column in source.source_entry.columns
            if column.type is not None
        }
    for seed in project.seeds:
        expected_types[(CompiledResourceType.SEED, seed.name)] = {
            column.name.casefold(): column.type
            for column in seed.schema_entry.columns
            if column.type is not None
        }
    for model_name in ordered_model_names:
        model: CompiledModel | None = model_map.get(model_name)
        if model is None:
            continue
        model_types: dict[str, str] = expected_types[(CompiledResourceType.MODEL, model_name)]
        for lineage_column in model.fast_lineage_columns or ():
            if lineage_column.transform_kind != ColumnTransformKind.DIRECT:
                continue
            upstream_types: set[str] = {
                upstream_type
                for upstream in lineage_column.upstream_columns
                if (
                    upstream_type := expected_types.get(
                        (CompiledResourceType(upstream.resource_type), upstream.resource_name), {}
                    ).get(upstream.column_name.casefold())
                )
            }
            if len(upstream_types) == 1:
                model_types.setdefault(
                    lineage_column.output_column.casefold(), upstream_types.pop()
                )
    type_fixture_groups: tuple[tuple[CompiledResourceType, dict[str, str]], ...] = (
        *fixture_groups,
        (CompiledResourceType.SQL_TEST, expected_outputs),
    )
    for resource_type, fixtures in type_fixture_groups:
        for name, sql in fixtures.items():
            inferred_columns: tuple[InferredColumn, ...] | None
            if resource_type == CompiledResourceType.SQL_TEST:
                inferred_columns = infer_fixture_columns(
                    query_sql=sql,
                    inference_profile=adapter.expression_inference_profile(),
                )
            else:
                inferred_columns = inferred_by_fixture.get((resource_type, name))
            if inferred_columns is None:
                continue
            type_key: tuple[CompiledResourceType, str] = (
                CompiledResourceType.MODEL
                if resource_type == CompiledResourceType.SQL_TEST
                else resource_type,
                name,
            )
            for column in inferred_columns:
                expected_type: str | None = expected_types.get(type_key, {}).get(
                    column.name.casefold()
                )
                if not _types_are_incompatible(expected=expected_type, inferred=column.type):
                    continue
                fixture_label: str = (
                    "expected output"
                    if resource_type == CompiledResourceType.SQL_TEST
                    else f"mock {resource_type.value}"
                )
                errors.append(
                    f"{_fixture_location(test=test, resource_type=resource_type, name=name)}: "
                    f"{fixture_label} '{name}' column '{column.name}' has incompatible type "
                    f"{column.type}; resource type is {expected_type}. Use an explicit CAST, "
                    "ARRAY_CONSTRUCT, or PARSE_JSON as appropriate"
                )
    if errors:
        raise SqlTestFixtureValidationError(
            tuple(f"SQL test '{test.name}': {diagnostic}" for diagnostic in sorted(set(errors)))
        )


def _fixture_location(
    *, test: CompiledSqlTest, resource_type: CompiledResourceType, name: str
) -> str:
    prefix: str = {
        CompiledResourceType.MODEL: "__ref__",
        CompiledResourceType.SOURCE: "__source__",
        CompiledResourceType.SEED: "__seed__",
        CompiledResourceType.SQL_TEST: "__expected__",
    }[resource_type]
    match: re.Match[str] | None = re.search(
        rf"(?im)^\s*{re.escape(prefix + name)}\s+AS\s*\(", test.test_file.contents
    )
    line: int = 1 if match is None else test.test_file.contents.count("\n", 0, match.start()) + 1
    return f"{test.test_file.relative_path.as_posix()}:{line}"


def _types_are_incompatible(*, expected: str | None, inferred: str | None) -> bool:
    if expected is None or inferred is None:
        return False
    expected_base: str = expected.upper().split("(", maxsplit=1)[0].strip()
    inferred_base: str = inferred.upper().split("(", maxsplit=1)[0].strip()
    return (expected_base in _COLLECTION_TYPES) != (inferred_base in _COLLECTION_TYPES)
