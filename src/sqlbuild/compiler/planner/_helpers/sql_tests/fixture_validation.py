"""Static SQL-test fixture shape validation."""

from __future__ import annotations

import re

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main._infer_fixture_columns import infer_fixture_columns
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompiledSqlTest,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.fixtures.completion import (
    build_relation_fixture_completion,
)
from sqlbuild.compiler.planner.exceptions import SqlTestFixtureValidationError
from sqlbuild.compiler.planner.models import (
    RelationFixtureCompletion,
    RelationFixtureDiagnostic,
)

_COLLECTION_TYPES: frozenset[str] = frozenset(
    {"ARRAY", "LIST", "MAP", "OBJECT", "STRUCT", "VARIANT"}
)


def build_validated_test_fixtures(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    adapter: BaseAdapter,
    ordered_model_names: tuple[str, ...],
    mock_refs: dict[str, str],
    mock_sources: dict[str, str],
    mock_seeds: dict[str, str],
    expected_outputs: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Report all statically provable missing columns and collection-type mismatches."""

    fixture_groups: tuple[tuple[CompiledResourceType, dict[str, str]], ...] = (
        (CompiledResourceType.MODEL, mock_refs),
        (CompiledResourceType.SOURCE, mock_sources),
        (CompiledResourceType.SEED, mock_seeds),
    )
    completion: RelationFixtureCompletion = build_relation_fixture_completion(
        project=project,
        adapter=adapter,
        ordered_model_names=ordered_model_names,
        fixture_groups=fixture_groups,
    )
    errors: list[str] = [
        _located_diagnostic(test=test, diagnostic=diagnostic)
        for diagnostic in completion.diagnostics
    ]
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
                inferred_columns = completion.inferred_by_fixture.get((resource_type, name))
            if inferred_columns is None:
                continue
            type_key: tuple[CompiledResourceType, str] = (
                CompiledResourceType.MODEL
                if resource_type == CompiledResourceType.SQL_TEST
                else resource_type,
                name,
            )
            for column in inferred_columns:
                expected_type: str | None = completion.expected_types.get(type_key, {}).get(
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
    return (
        _completed_fixture_group(
            resource_type=CompiledResourceType.MODEL,
            fixtures=mock_refs,
            completion=completion,
        ),
        _completed_fixture_group(
            resource_type=CompiledResourceType.SOURCE,
            fixtures=mock_sources,
            completion=completion,
        ),
        _completed_fixture_group(
            resource_type=CompiledResourceType.SEED,
            fixtures=mock_seeds,
            completion=completion,
        ),
    )


def _located_diagnostic(*, test: CompiledSqlTest, diagnostic: RelationFixtureDiagnostic) -> str:
    return (
        f"{_fixture_location(test=test, resource_type=diagnostic.key[0], name=diagnostic.key[1])}: "
        f"{diagnostic.message}"
    )


def _completed_fixture_group(
    *,
    resource_type: CompiledResourceType,
    fixtures: dict[str, str],
    completion: RelationFixtureCompletion,
) -> dict[str, str]:
    return {
        name: completion.fixture_sql_by_key.get((resource_type, name), sql)
        for name, sql in fixtures.items()
    }


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
