"""Contract-aware formatting of SQL test fixture projections."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.constants import (
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.main._infer_fixture_columns import infer_fixture_column_facts
from sqlbuild.compiler.compile.models import (
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompiledSqlTest,
    CompileSqlTestCte,
    FixtureColumnInference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlTestMode
from sqlbuild.compiler.planner._helpers.fixtures.completion import (
    build_relation_fixture_completion,
    build_relation_fixture_context,
)
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import (
    build_sql_test_planning_context,
)
from sqlbuild.compiler.planner.models import (
    FixtureColumnMetadata,
    FixtureRelationMetadata,
    RelationFixtureCompletion,
    RelationFixturePlanningContext,
    SqlTestPlanningContext,
)
from sqlbuild.compiler.planner.types import FixtureGroups, FixtureKey

_TYPED_NULL_LINE_PATTERN: re.Pattern[str] = re.compile(
    r"^(?P<indent>[ \t]*)(?:"
    r"CAST\s*\(\s*NULL\s+AS\s+(?P<cast_type>"
    r"[A-Za-z_][A-Za-z0-9_]*(?:\s*\([^()]*\))?"
    r"(?:\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*\([^()]*\))?)*"
    r")\)"
    r"|NULL\s*::\s*(?P<colon_type>[A-Za-z_][A-Za-z0-9_]*(?:\([^)]*\))?)"
    r")\s+AS\s+(?P<alias>\"[^\"]+\"|`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P<comma>\s*,)?[ \t]*$",
    re.IGNORECASE,
)
_CLAUSE_LINE_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*(?:FROM|WHERE|GROUP|HAVING|QUALIFY|ORDER|LIMIT|UNION|INTERSECT|EXCEPT)\b",
    re.IGNORECASE,
)
_SET_OPERATION_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:UNION|INTERSECT|EXCEPT)\b", re.IGNORECASE
)


def format_redundant_fixture_nulls(
    *,
    files: dict[Path, str],
    project_dir: Path,
    project: CompiledProject,
    adapter: BaseAdapter,
) -> dict[Path, str]:
    """Remove typed-null fixture projections that planner completion can reproduce."""

    planning_context: SqlTestPlanningContext = build_sql_test_planning_context(
        project=project,
        tests=project.sql_tests,
    )
    fixture_context: RelationFixturePlanningContext = build_relation_fixture_context(
        project=project
    )
    updated: dict[Path, str] = {}
    processed_blocks: set[tuple[Path, int]] = set()
    for test in project.sql_tests:
        source_path: Path | None = test.source_path
        block_index: int | None = test.block_index
        if source_path is None or block_index is None:
            continue
        block_key: tuple[Path, int] = (source_path, block_index)
        if block_key in processed_blocks or test.mode is not SqlTestMode.MODEL:
            continue
        processed_blocks.add(block_key)
        file_path: Path = (project_dir / source_path).resolve()
        contents: str | None = updated.get(file_path, files.get(file_path))
        if contents is None:
            continue
        fixed_block: str = _format_test_block(
            test=test,
            project=project,
            adapter=adapter,
            planning_context=planning_context,
            fixture_context=fixture_context,
        )
        if fixed_block == test.test_block.sql_body:
            continue
        rewritten: str = _replace_test_block(
            contents=contents,
            original=test.test_block.sql_body,
            replacement=fixed_block,
        )
        if rewritten != contents:
            updated[file_path] = rewritten
    return updated


def _format_test_block(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    adapter: BaseAdapter,
    planning_context: SqlTestPlanningContext,
    fixture_context: RelationFixturePlanningContext,
) -> str:
    payload: object = test.payload
    if not isinstance(payload, CompiledModelSqlTestPayload):
        return test.test_block.sql_body
    if test.sql_body != test.test_block.sql_body:
        return test.test_block.sql_body
    ordered_model_names: tuple[str, ...] | None = planning_context.chain_names_by_test_key.get(
        test.key
    )
    if ordered_model_names is None:
        return test.test_block.sql_body
    fixture_ctes: tuple[CompileSqlTestCte, ...] = tuple(
        cte for cte in payload.authored_ctes if _fixture_key(cte.name) is not None
    )
    fixture_sql: dict[tuple[CompiledResourceType, str], str] = {
        key: cte.sql_body for cte in fixture_ctes if (key := _fixture_key(cte.name)) is not None
    }
    changed_bodies: list[tuple[str, str]] = []
    for cte in fixture_ctes:
        key: FixtureKey | None = _fixture_key(cte.name)
        if key is None:
            continue
        relation: FixtureRelationMetadata | None = fixture_context.relations.get(key)
        if relation is None or not relation.authoritative_names:
            continue
        candidate: str = _remove_redundant_typed_null_lines(
            sql=fixture_sql[key],
            relation=relation,
            adapter=adapter,
        )
        if candidate == fixture_sql[key]:
            continue
        candidate_fixture_sql: dict[tuple[CompiledResourceType, str], str] = {
            **fixture_sql,
            key: candidate,
        }
        completion: RelationFixtureCompletion = build_relation_fixture_completion(
            project=project,
            adapter=adapter,
            ordered_model_names=ordered_model_names,
            fixture_groups=_fixture_groups(candidate_fixture_sql),
            planning_context=fixture_context,
        )
        if completion.diagnostics:
            continue
        fixture_sql[key] = candidate
        changed_bodies.append((cte.sql_body, candidate))
    if not changed_bodies:
        return test.test_block.sql_body
    return _replace_cte_bodies(
        sql=test.test_block.sql_body,
        replacements=tuple(changed_bodies),
    )


def _remove_redundant_typed_null_lines(
    *, sql: str, relation: FixtureRelationMetadata, adapter: BaseAdapter
) -> str:
    if _SET_OPERATION_PATTERN.search(sql) is not None:
        return sql
    metadata_by_name: dict[str, FixtureColumnMetadata] = {
        column.name.casefold(): column for column in relation.columns
    }
    lines: list[str] = sql.splitlines()
    typed_null_indexes: set[int] = set()
    remove_indexes: set[int] = set()
    for index, line in enumerate(lines):
        match: re.Match[str] | None = _TYPED_NULL_LINE_PATTERN.fullmatch(line)
        if match is None:
            continue
        alias: str = match.group("alias").strip('"`')
        column: FixtureColumnMetadata | None = metadata_by_name.get(alias.casefold())
        if column is None or column.type is None:
            continue
        typed_null_indexes.add(index)
        if column.nullable is False:
            continue
        remove_indexes.add(index)
    empty_retained: list[str] = [
        line for index, line in enumerate(lines) if index not in typed_null_indexes
    ]
    empty_retained = _without_trailing_projection_comma(lines=empty_retained)
    empty_candidate: str = "\n".join(empty_retained)
    if re.fullmatch(r"\s*SELECT\s+WHERE\s+FALSE\s*", empty_candidate, re.IGNORECASE):
        return "SELECT * FROM __empty_fixture()"
    if not remove_indexes:
        return sql
    retained: list[str] = [line for index, line in enumerate(lines) if index not in remove_indexes]
    retained = _without_trailing_projection_comma(lines=retained)
    candidate: str = "\n".join(retained)
    inference: FixtureColumnInference | None = infer_fixture_column_facts(
        query_sql=candidate,
        inference_profile=adapter.expression_inference_profile(),
    )
    if inference is None or not inference.columns:
        return sql
    return candidate


def _without_trailing_projection_comma(*, lines: list[str]) -> list[str]:
    updated: list[str] = list(lines)
    clause_index: int | None = next(
        (index for index, line in enumerate(updated) if _CLAUSE_LINE_PATTERN.match(line)),
        None,
    )
    search_end: int = len(updated) if clause_index is None else clause_index
    for index in range(search_end - 1, -1, -1):
        if not updated[index].strip():
            continue
        updated[index] = re.sub(r",\s*$", "", updated[index])
        break
    return updated


def _fixture_key(name: str) -> tuple[CompiledResourceType, str] | None:
    for prefix, resource_type in (
        (REF_TEST_CTE_PREFIX, CompiledResourceType.MODEL),
        (SOURCE_TEST_CTE_PREFIX, CompiledResourceType.SOURCE),
        (SEED_TEST_CTE_PREFIX, CompiledResourceType.SEED),
    ):
        if name.startswith(prefix):
            return resource_type, name.removeprefix(prefix)
    return None


def _fixture_groups(
    fixture_sql: dict[tuple[CompiledResourceType, str], str],
) -> FixtureGroups:
    groups: list[tuple[CompiledResourceType, dict[str, str]]] = []
    resource_types: tuple[CompiledResourceType, ...] = (
        CompiledResourceType.MODEL,
        CompiledResourceType.SOURCE,
        CompiledResourceType.SEED,
    )
    for resource_type in resource_types:
        fixtures: dict[str, str] = {}
        for (candidate_type, name), sql in fixture_sql.items():
            if candidate_type == resource_type:
                fixtures[name] = sql
        groups.append((resource_type, fixtures))
    return tuple(groups)


def _replace_cte_bodies(*, sql: str, replacements: tuple[tuple[str, str], ...]) -> str:
    result: str = sql
    for original, replacement in replacements:
        if result.count(original) != 1:
            continue
        result = result.replace(original, replacement, 1)
    return result


def _replace_test_block(*, contents: str, original: str, replacement: str) -> str:
    start: int = contents.find(original)
    if start < 0:
        return contents
    return f"{contents[:start]}{replacement}{contents[start + len(original) :]}"
