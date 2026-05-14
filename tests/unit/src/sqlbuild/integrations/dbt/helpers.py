from __future__ import annotations

import json
from pathlib import Path

from sqlbuild.compiler.compile.helpers.assembly import assemble_compiled_project
from sqlbuild.compiler.compile.helpers.refs import extract_sql_references
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompileModelConfig,
    CompileModelInput,
    CompileProjectInputs,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlModelFile
from sqlbuild.compiler.planner.models import BackfillResult, ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.integrations.dbt.helpers.graph import dbt_model_graph_key, sqlbuild_model_graph_key
from sqlbuild.integrations.dbt.helpers.runner import build_dbt_ls_argv
from sqlbuild.integrations.dbt.models import (
    DbtCliConfigOverrides,
    DbtCliOptions,
    DbtCombinedGraphKey,
    DbtCommandResult,
)
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


def build_cli_overrides(
    *,
    project_dir: str | None = None,
    profiles_dir: str | None = None,
    target: str | None = None,
    target_path: str | None = None,
) -> DbtCliConfigOverrides:
    """Build dbt CLI config overrides for tests."""

    return DbtCliConfigOverrides(
        project_dir=project_dir,
        profiles_dir=profiles_dir,
        target=target,
        target_path=target_path,
    )


def build_dbt_cli_options(project_root: Path) -> DbtCliOptions:
    """Build representative dbt options for argv tests."""

    return DbtCliOptions(
        project_dir=project_root / "dbt",
        profiles_dir=project_root / "profiles",
        target="prod",
        target_path=project_root / "target/dbt",
        vars='{"run_date":"2026-01-01"}',
        state=project_root / "state",
        defer=True,
    )


class RecordingDbtInvoker:
    """Record dbt invocations and return a fixed result."""

    def __init__(self, result: DbtCommandResult) -> None:
        self.result = result
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []

    def __call__(self, argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        self.calls.append((argv, cwd))
        return self.result


class MappingDbtInvoker:
    """Record dbt invocations and return results by argv."""

    def __init__(self, results_by_argv: dict[tuple[str, ...], DbtCommandResult]) -> None:
        self.results_by_argv = results_by_argv
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []

    def __call__(self, argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        self.calls.append((argv, cwd))
        result: DbtCommandResult | None = self.results_by_argv.get(argv)
        if result is not None:
            return result
        return DbtCommandResult(argv=argv, returncode=0, stdout="")


def build_dbt_ls_command_result(
    *, argv: tuple[str, ...], unique_ids: tuple[str, ...]
) -> DbtCommandResult:
    """Build a dbt ls command result with JSON-lines nodes."""

    stdout: str = "\n".join(json.dumps({"unique_id": unique_id}) for unique_id in unique_ids)
    return DbtCommandResult(argv=argv, returncode=0, stdout=stdout)


def build_sqlbuild_plan_output(model_names: tuple[str, ...]) -> PlanOutput:
    """Build a minimal SQLBuild plan output for dbt formatter tests."""

    return PlanOutput(
        model_entries=tuple(
            _build_sqlbuild_model_plan_entry(model_name) for model_name in model_names
        )
    )


def _build_sqlbuild_model_plan_entry(model_name: str) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL,
            name=model_name,
        ),
        name=model_name,
        relative_path=Path(f"models/{model_name}.sql"),
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.NO_CHANGE,
        target=CompiledRelationTarget(
            database=None,
            schema=None,
            name=model_name,
            qualified_name=None,
        ),
        fingerprint_query_sql="select 1",
        resolved_sql="select 1",
        logical_ddl="",
        backfill=BackfillResult(action=BackfillAction.WARN_ONLY),
    )


def build_dbt_plan_mapping_invoker(
    *,
    options: DbtCliOptions,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    full_dbt_ls_unique_ids: tuple[str, ...],
    anchor_dbt_ls_unique_ids_by_term: dict[str, tuple[str, ...]],
) -> MappingDbtInvoker:
    """Build a mapping invoker for plan orchestration dbt ls calls."""

    results_by_argv: dict[tuple[str, ...], DbtCommandResult] = {}
    full_argv: tuple[str, ...] = build_dbt_ls_argv(
        dbt_executable="dbt",
        options=options,
        select=select,
        exclude=exclude,
    )
    results_by_argv[full_argv] = build_dbt_ls_command_result(
        argv=full_argv,
        unique_ids=full_dbt_ls_unique_ids,
    )
    term: str
    unique_ids: tuple[str, ...]
    for term, unique_ids in anchor_dbt_ls_unique_ids_by_term.items():
        anchor_argv: tuple[str, ...] = build_dbt_ls_argv(
            dbt_executable="dbt",
            options=options,
            select=(term,),
            exclude=exclude,
        )
        results_by_argv[anchor_argv] = build_dbt_ls_command_result(
            argv=anchor_argv,
            unique_ids=unique_ids,
        )
    return MappingDbtInvoker(results_by_argv=results_by_argv)


def extract_dbt_ls_selects(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Extract select terms from a dbt ls argv for assertions."""

    if "--select" not in argv:
        return ()
    values: list[str] = []
    index: int = argv.index("--select") + 1
    while index < len(argv) and not argv[index].startswith("--"):
        values.append(argv[index])
        index += 1
    return tuple(values)


def extract_dbt_ls_excludes(argv: tuple[str, ...]) -> tuple[str, ...]:
    """Extract exclude terms from a dbt ls argv for assertions."""

    if "--exclude" not in argv:
        return ()
    values: list[str] = []
    index: int = argv.index("--exclude") + 1
    while index < len(argv) and not argv[index].startswith("--"):
        values.append(argv[index])
        index += 1
    return tuple(values)


def build_manifest_data(*, nodes: tuple[dict[str, object], ...]) -> dict[str, object]:
    """Build a minimal dbt manifest payload for model lookup tests."""

    return {"nodes": {str(node["unique_id"]): node for node in nodes}}


def build_manifest_model_node(
    *,
    unique_id: str,
    package_name: str,
    name: str,
    relation_name: str | None = None,
    database: str | None = None,
    schema: str | None = None,
    alias: str | None = None,
    depends_on_nodes: tuple[str, ...] = (),
) -> dict[str, object]:
    """Build a minimal dbt manifest model node."""

    node: dict[str, object] = {
        "unique_id": unique_id,
        "resource_type": "model",
        "package_name": package_name,
        "name": name,
    }
    if relation_name is not None:
        node["relation_name"] = relation_name
    if database is not None:
        node["database"] = database
    if schema is not None:
        node["schema"] = schema
    if alias is not None:
        node["alias"] = alias
    if depends_on_nodes:
        node["depends_on"] = {"nodes": list(depends_on_nodes)}
    return node


def build_compiled_project_with_models(sql_by_model_name: dict[str, str]) -> CompiledProject:
    """Build a minimal compiled project from model SQL strings."""

    return build_compiled_project_with_model_specs(
        sql_by_model_name=sql_by_model_name,
        tags_by_model_name={},
        path_by_model_name={},
    )


def build_compiled_project_with_model_specs(
    *,
    sql_by_model_name: dict[str, str],
    tags_by_model_name: dict[str, tuple[str, ...]],
    path_by_model_name: dict[str, str],
) -> CompiledProject:
    """Build a minimal compiled project from model SQL, tags, and relative paths."""

    model_inputs: list[CompileModelInput] = []
    model_name: str
    sql: str
    for model_name, sql in sql_by_model_name.items():
        relative_path: Path = Path(path_by_model_name.get(model_name, f"models/{model_name}.sql"))
        model_file: DiscoveredSqlModelFile = DiscoveredSqlModelFile(
            file_path=Path("/repo") / relative_path,
            relative_path=relative_path,
            contents=f"MODEL ();\n\n{sql}\n",
            header_values={},
            header_column_locations={},
            output_column_locations={},
            query_sql=sql,
        )
        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
                config=CompileModelConfig(
                    values={"tags": tags_by_model_name.get(model_name, ())}
                    if model_name in tags_by_model_name
                    else {}
                ),
                query_sql=sql,
                references=extract_sql_references(sql),
            )
        )
    return assemble_compiled_project(
        CompileProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            discovered_inputs=DiscoveredProjectInputs(
                project_config=ProjectConfig(name="demo", adapter="duckdb"),
                local_config=LocalConfig(),
            ),
            model_inputs=tuple(model_inputs),
        )
    )


def graph_edge_stable_ids(
    graph_edges: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
) -> dict[str, tuple[str, ...]]:
    """Render graph edges as stable IDs for assertions."""

    return {
        key.stable_id: tuple(dep.stable_id for dep in deps) for key, deps in graph_edges.items()
    }


def graph_key_stable_ids(keys: frozenset[DbtCombinedGraphKey]) -> tuple[str, ...]:
    """Render graph keys as sorted stable IDs for assertions."""

    return tuple(sorted(key.stable_id for key in keys))


def graph_key_from_stable_id(stable_id: str) -> DbtCombinedGraphKey:
    """Build a graph key from its stable string form."""

    owner, _resource_type, name = stable_id.split(":", maxsplit=2)
    if owner == "dbt":
        return dbt_model_graph_key(name)
    return sqlbuild_model_graph_key(name)
