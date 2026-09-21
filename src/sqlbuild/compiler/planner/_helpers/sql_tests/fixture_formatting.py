"""Contract-aware formatting of SQL test fixture projections."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.compiler.compile.classes.sql_test_cte_extractor import SqlTestCteExtractor
from sqlbuild.compiler.compile.constants import (
    REF_TEST_CTE_PREFIX,
    SEED_TEST_CTE_PREFIX,
    SOURCE_TEST_CTE_PREFIX,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlTestCte
from sqlbuild.compiler.compile.types import CompiledResourceType, SqlTestMode
from sqlbuild.compiler.discovery.main._model_schema_columns import parse_schema_columns
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
from sqlbuild.spec.contracts.models import SchemaColumn, SchemaSeedEntry, SourceEntry

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
_MACRO_INVOCATION_MARKER: str = "@"
_TYPED_NULL_CANDIDATE_PATTERN: re.Pattern[str] = re.compile(
    r"(?:CAST\s*\(\s*NULL\s+AS\b|NULL\s*::)", re.IGNORECASE
)
_PROJECTION_ALIAS_PATTERN: re.Pattern[str] = re.compile(
    r"\bAS\s+(?P<alias>\"[^\"]+\"|`[^`]+`|[A-Za-z_][A-Za-z0-9_]*)\s*,?\s*$",
    re.IGNORECASE,
)
_SELECT_LINE_PATTERN: re.Pattern[str] = re.compile(r"^\s*SELECT\b(?P<body>.*)$", re.IGNORECASE)


def format_redundant_fixture_nulls(
    *,
    files: dict[Path, str],
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
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
        block: DiscoveredSqlTestBlock
        for block in test_file.blocks:
            fixed_block: str = _format_test_block(
                block=block,
                file_label=str(test_file.relative_path),
                relations=relations,
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
        columns: tuple[SchemaColumn, ...] = parse_schema_columns(
            raw_columns=model_file.header_values.get("columns"),
            file_path=model_file.file_path,
            label="model",
            error_class=CompileInputError,
            column_locations=model_file.header_column_locations,
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


def _remove_redundant_typed_null_lines(*, sql: str, relation: FixtureRelationMetadata) -> str:
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
    authored_names: tuple[str, ...] | None = _projection_aliases(lines=lines)
    if authored_names is None or not _names_form_schema_prefix(
        names=authored_names,
        relation=relation,
    ):
        return sql
    retained: list[str] = [line for index, line in enumerate(lines) if index not in remove_indexes]
    retained = _without_trailing_projection_comma(lines=retained)
    candidate: str = "\n".join(retained)
    retained_names: tuple[str, ...] | None = _projection_aliases(lines=retained)
    if retained_names is None or not retained_names:
        return sql
    if not _names_form_schema_prefix(names=retained_names, relation=relation):
        return sql
    return candidate


def _projection_aliases(*, lines: list[str]) -> tuple[str, ...] | None:
    aliases: list[str] = []
    saw_select: bool = False
    for line in lines:
        candidate: str = line
        if not saw_select:
            select_match: re.Match[str] | None = _SELECT_LINE_PATTERN.match(line)
            if select_match is None:
                if line.strip():
                    return None
                continue
            saw_select = True
            candidate = select_match.group("body")
        if _CLAUSE_LINE_PATTERN.match(candidate):
            break
        if not candidate.strip():
            continue
        alias_match: re.Match[str] | None = _PROJECTION_ALIAS_PATTERN.search(candidate)
        if alias_match is None:
            return None
        aliases.append(alias_match.group("alias").strip('"`').casefold())
    return tuple(aliases) if saw_select else None


def _names_form_schema_prefix(*, names: tuple[str, ...], relation: FixtureRelationMetadata) -> bool:
    schema_prefix: tuple[str, ...] = tuple(
        column.name.casefold() for column in relation.columns[: len(names)]
    )
    return names == schema_prefix


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
