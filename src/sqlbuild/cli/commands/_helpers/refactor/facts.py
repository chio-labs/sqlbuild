"""Plain-data compiler facts the native refactoring planner reads.

This is the only refactor module that reads `CompiledProject`. Once the native command core
returns project facts (M5 PR B), these facts come from it instead.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections.abc import Callable
from pathlib import Path

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledSqlExpansion,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredProjectInputs,
    DiscoveredSqlTestBlock,
)
from sqlbuild.compiler.frontier.main.report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite
from sqlbuild.compiler.refactoring.constants import GENERIC_DIALECT, MIGRATE_FROM_KEY
from sqlbuild.compiler.refactoring.main.find_python_string_locations import (
    find_python_string_locations,
)
from sqlbuild.compiler.refactoring.main.plan_declaration_moves import plan_declaration_moves
from sqlbuild.compiler.refactoring.models import ManualLocation, RefactorProject, RefactorRequest
from sqlbuild.compiler.refactoring.types import RefactorOperation, SqlFileRole
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.models import SchemaColumn, SourceColumnEntry

_MATERIALIZED_KEY: str = "materialized"


def refactor_facts_json(*, project: RefactorProject, request: RefactorRequest) -> str:
    """Return the facts one refactoring plan reads, as the native planner's JSON."""

    compiled: CompiledProject = project.graph.project
    discovered: DiscoveredProjectInputs = project.discovered
    return json.dumps(
        {
            "project_dir": str(project.project_dir),
            "dialect": compiled.sql_analysis_dialect or GENERIC_DIALECT,
            "python_version": list(sys.version_info[:2]),
            "unicode_version": unicodedata.unidata_version,
            "models": model_facts(project=compiled, project_dir=project.project_dir),
            "sources": [
                _columns(name=source.name, columns=source.source_entry.columns)
                for source in compiled.sources
            ],
            "seeds": [
                _columns(name=seed.name, columns=seed.schema_entry.columns)
                for seed in compiled.seeds
            ],
            "model_files": [
                {"path": item.relative_path.as_posix(), "contents": item.contents}
                for item in discovered.model_files
            ],
            "authored_files": _authored_files(discovered=discovered),
            "yaml_files": [
                {"path": item.relative_path.as_posix(), "contents": item.contents}
                for item in (*discovered.source_files, *discovered.schema_files)
            ],
            "python_locations": [
                _location(item) for item in _python_locations(project=project, request=request)
            ],
        }
    )


def model_facts_json(*, project: RefactorProject | None) -> str | None:
    """Return the model facts of one compiled project as JSON, or None without a project."""

    if project is None:
        return None
    return json.dumps(model_facts(project=project.graph.project, project_dir=project.project_dir))


def model_facts(*, project: CompiledProject, project_dir: Path) -> list[dict[str, object]]:
    """Return every compiled model's refactoring facts."""

    expansions: dict[Path, CompiledSqlExpansion] = {
        path.resolve(): expansion for path, expansion in reversed(project.sql_expansions.items())
    }
    return [
        _model(model=model, expansion=expansions.get((project_dir / model.relative_path).resolve()))
        for model in project.models
    ]


def declaration_moves_host(*, project: RefactorProject) -> Callable[[str, str, str], str]:
    """Return the host callback that works out declaration moves with the Python scope index."""

    def moves(model_name: str, source_path: str, destination: str) -> str:
        report_native_fallback(site=NativeFallbackSite.REFACTOR_DECLARATION_MOVES)
        found: tuple[tuple[tuple[str, str], ...], tuple[ManualLocation, ...]] = (
            plan_declaration_moves(
                project=project,
                model_name=model_name,
                source_path=source_path,
                destination=destination,
            )
        )
        return json.dumps(
            {
                "moves": [list(item) for item in found[0]],
                "blocking": [_location(item) for item in found[1]],
            }
        )

    return moves


def _model(*, model: CompiledModel, expansion: CompiledSqlExpansion | None) -> dict[str, object]:
    values: dict[str, object] = dict(model.config.values)
    return {
        "name": model.name,
        "path": model.relative_path.as_posix(),
        "deps": [
            {"resource_type": dep.resource_type.value, "name": dep.name} for dep in model.deps
        ],
        "query_sql": model.query_sql,
        "authored_query_sql": model.authored_query_sql,
        "materialized": get_config_str(values=values, key=_MATERIALIZED_KEY),
        "declares_migrate_from": MIGRATE_FROM_KEY in values,
        "migrate_from_set": values.get(MIGRATE_FROM_KEY) is not None,
        "destination": {
            "database": model.destination.database,
            "schema": model.destination.schema,
            "name": model.destination.name,
        },
        "inferred_columns": [column.name for column in model.inferred_columns or ()],
        "schema_columns": (
            [
                {
                    "name": column.name,
                    "migrate_from": column.migrate_from is not None,
                    "location": (
                        {
                            "path": column.location.path.as_posix(),
                            "line": column.location.line,
                            "column": column.location.column,
                        }
                        if column.location is not None
                        else None
                    ),
                }
                for column in model.schema_entry.columns
            ]
            if model.schema_entry is not None
            else None
        ),
        "expansion": (
            {
                "expanded_sql": expansion.expanded_sql,
                "passes": [
                    [
                        {
                            "source_start": span.source_start,
                            "source_end": span.source_end,
                            "output_start": span.output_start,
                            "output_end": span.output_end,
                        }
                        for span in spans
                    ]
                    for spans in expansion.passes
                ],
            }
            if expansion is not None
            else None
        ),
    }


def _authored_files(*, discovered: DiscoveredProjectInputs) -> list[dict[str, object]]:
    files: list[tuple[SqlFileRole, Path, str, tuple[str, ...]]] = [
        *(
            (SqlFileRole.TEST, item.relative_path, item.contents, _block_bodies(item.blocks))
            for item in discovered.test_files
        ),
        *(
            (SqlFileRole.SCENARIO, item.relative_path, item.contents, (item.sql_body,))
            for item in discovered.scenario_files
        ),
        *(
            (SqlFileRole.AUDIT, item.relative_path, item.contents, _block_bodies(item.blocks))
            for item in discovered.audit_files
        ),
        *(
            (SqlFileRole.HOOK, item.relative_path, item.contents, (item.sql_body,))
            for item in discovered.sql_hook_files
        ),
        *(
            (SqlFileRole.FUNCTION, item.relative_path, item.contents, (item.body_sql,))
            for item in discovered.sql_function_files
        ),
        *(
            (SqlFileRole.SCHEMA, item.relative_path, item.contents, ())
            for item in discovered.model_schema_files
        ),
    ]
    return [
        {"role": role.value, "path": path.as_posix(), "contents": contents, "texts": list(texts)}
        for role, path, contents, texts in files
    ]


def _block_bodies(
    blocks: tuple[DiscoveredSqlTestBlock | DiscoveredAuditBlock, ...],
) -> tuple[str, ...]:
    return tuple(block.sql_body for block in blocks)


def _columns(
    *, name: str, columns: tuple[SchemaColumn | SourceColumnEntry, ...]
) -> dict[str, object]:
    return {"name": name, "columns": [column.name for column in columns]}


def _python_locations(
    *, project: RefactorProject, request: RefactorRequest
) -> tuple[ManualLocation, ...]:
    old: str = request.model_name
    if request.operation == RefactorOperation.RENAME_COLUMN:
        column: str = request.column_name or ""
        return find_python_string_locations(
            project_dir=project.project_dir,
            discovered=project.discovered,
            names=(column,),
            reason=f"Python SQL may read column {column} of {old}; check it by hand",
            context=old,
        )
    return find_python_string_locations(
        project_dir=project.project_dir,
        discovered=project.discovered,
        names=(old,),
        reason=f"Python code names model {old}; update it by hand",
    )


def _location(location: ManualLocation) -> dict[str, object]:
    return {
        "path": location.path,
        "line": location.line,
        "column": location.column,
        "reason": location.reason,
    }
