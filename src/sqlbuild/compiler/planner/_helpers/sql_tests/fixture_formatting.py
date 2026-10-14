"""Contract-aware formatting of SQL test fixture projections."""

from __future__ import annotations

import re
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild._native import simplify_fixture_null_projections as _remove_redundant_typed_null_lines
from sqlbuild.compiler.compile.classes.sql_test_cte_extractor import SqlTestCteExtractor
from sqlbuild.compiler.compile.constants import (
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlTestCte
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlTestMode
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSqlModelFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
from sqlbuild.compiler.path_defaults.main._select import select_path_default
from sqlbuild.compiler.planner.models import (
    FixtureColumnMetadata,
    FixtureRelationMetadata,
)
from sqlbuild.compiler.planner.types import ContractPolicy, FixtureKey
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.spec.contracts.models import SchemaColumn, SchemaSeedEntry, SourceEntry

_MACRO_INVOCATION_MARKER: str = "@"
_TYPED_NULL_CANDIDATE_PATTERN: re.Pattern[str] = re.compile(
    r"(?:CAST\s*\(\s*NULL\s+AS\b|NULL\s*::)", re.IGNORECASE
)


def format_redundant_fixture_nulls(
    *,
    files: dict[Path, str],
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    sql_lexical_syntax: SqlLexicalSyntax,
) -> dict[Path, str]:
    """Remove typed-null fixture projections that planner completion can reproduce."""

    relations: dict[FixtureKey, FixtureRelationMetadata] = _fixture_relations(
        discovered_inputs=discovered_inputs
    )
    updated: dict[Path, str] = {}
    test_file: DiscoveredSqlTestFile
    for test_file in discovered_inputs.test_files:
        file_path: Path = (project_dir / test_file.relative_path).resolve()
        if file_path not in files:
            continue
        contents: str | None = updated.get(file_path, files.get(file_path))
        if contents is None:
            continue
        try:
            current_blocks: tuple[DiscoveredSqlTestBlock, ...] = _native.parse_sql_test_file(
                contents=contents,
                file_path=file_path,
            )
        except (OSError, UnicodeError, ValueError, SyntaxError):
            continue
        block: DiscoveredSqlTestBlock
        for block in current_blocks:
            fixed_block: str = _format_test_block(
                block=block,
                file_label=str(test_file.relative_path),
                relations=relations,
                syntax=sql_lexical_syntax,
            )
            if fixed_block == block.sql_body:
                continue
            contents = _replace_test_block(
                contents=contents,
                original=block.sql_body,
                replacement=fixed_block,
            )
            updated[file_path] = contents
    return updated


def _format_test_block(
    *,
    block: DiscoveredSqlTestBlock,
    file_label: str,
    relations: dict[FixtureKey, FixtureRelationMetadata],
    syntax: SqlLexicalSyntax,
) -> str:
    if (
        block.mode is not SqlTestMode.MODEL
        or _MACRO_INVOCATION_MARKER in block.sql_body
        or _TYPED_NULL_CANDIDATE_PATTERN.search(block.sql_body) is None
    ):
        return block.sql_body
    try:
        authored_ctes: tuple[CompileSqlTestCte, ...] = SqlTestCteExtractor.extract(
            sql=block.sql_body,
            file_label=file_label,
            syntax=syntax,
        )
    except CompileInputError:
        return block.sql_body
    changed_bodies: list[tuple[str, str]] = []
    for cte in authored_ctes:
        key: FixtureKey | None = _fixture_key(cte.name)
        if key is None:
            continue
        relation: FixtureRelationMetadata | None = relations.get(key)
        if relation is None or not relation.authoritative_names:
            continue
        candidate: str = _remove_redundant_typed_null_lines(
            sql=cte.sql_body,
            relation=relation,
        )
        if candidate == cte.sql_body:
            continue
        changed_bodies.append((cte.sql_body, candidate))
    if not changed_bodies:
        return block.sql_body
    return _replace_cte_bodies(
        sql=block.sql_body,
        replacements=tuple(changed_bodies),
    )


def _fixture_relations(
    *, discovered_inputs: DiscoveredProjectInputs
) -> dict[FixtureKey, FixtureRelationMetadata]:
    relations: dict[FixtureKey, FixtureRelationMetadata] = {}
    default_contract: str | None = discovered_inputs.project_config.defaults.contract
    path_defaults: dict[str, dict[str, object]] = discovered_inputs.project_config.path_defaults
    model_file: DiscoveredSqlModelFile
    for model_file in discovered_inputs.model_files:
        selected_default: str | None = select_path_default(
            model_path=str(model_file.relative_path),
            path_keys=tuple(path_defaults),
        ).selected_key
        contract: object = default_contract
        if selected_default is not None:
            contract = path_defaults[selected_default].get("contract", contract)
        contract = model_file.header_values.get("contract", contract)
        if contract != ContractPolicy.ENFORCED.value:
            continue
        columns: tuple[SchemaColumn, ...] = _native.parse_schema_columns(
            model_file.header_values.get("columns"),
            (str(model_file.file_path), "model"),
            (False, True, False),
            model_file.header_column_locations,
        )
        if not columns:
            continue
        relations[(CompiledResourceType.MODEL, model_file.file_path.stem)] = _relation_metadata(
            columns=columns
        )
    for source_file in discovered_inputs.source_files:
        source: SourceEntry
        for source in source_file.source_entries:
            source_contract: str | None = source.contract or default_contract
            if source_contract != ContractPolicy.ENFORCED.value:
                continue
            relations[(CompiledResourceType.SOURCE, source.name)] = FixtureRelationMetadata(
                columns=tuple(
                    FixtureColumnMetadata(
                        name=column.name,
                        type=column.type,
                        nullable=column.nullable,
                    )
                    for column in source.columns
                ),
                authoritative_names=bool(source.columns),
            )
    for schema_file in discovered_inputs.schema_files:
        seed: SchemaSeedEntry
        for seed in schema_file.seed_entries:
            if seed.columns:
                relations[(CompiledResourceType.SEED, seed.name)] = _relation_metadata(
                    columns=seed.columns
                )
    return relations


def _relation_metadata(*, columns: tuple[SchemaColumn, ...]) -> FixtureRelationMetadata:
    return FixtureRelationMetadata(
        columns=tuple(
            FixtureColumnMetadata(
                name=column.name,
                type=column.type,
                nullable=column.nullable,
            )
            for column in columns
        ),
        authoritative_names=True,
    )


def _fixture_key(name: str) -> tuple[CompiledResourceType, str] | None:
    for prefix, resource_type in (
        (REF_TEST_CTE_PREFIX, CompiledResourceType.MODEL),
        (SOURCE_TEST_CTE_PREFIX, CompiledResourceType.SOURCE),
        (SEED_TEST_CTE_PREFIX, CompiledResourceType.SEED),
    ):
        if name.startswith(prefix):
            return resource_type, name.removeprefix(prefix)
    return None


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
