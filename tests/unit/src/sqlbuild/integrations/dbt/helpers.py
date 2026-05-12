from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.helpers.assembly import assemble_compiled_project
from sqlbuild.compiler.compile.helpers.refs import extract_sql_references
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompileModelInput,
    CompileProjectInputs,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlModelFile
from sqlbuild.integrations.dbt.helpers.graph import dbt_model_graph_key, sqlbuild_model_graph_key
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

    model_inputs: list[CompileModelInput] = []
    model_name: str
    sql: str
    for model_name, sql in sql_by_model_name.items():
        model_file: DiscoveredSqlModelFile = DiscoveredSqlModelFile(
            file_path=Path("/repo/models") / f"{model_name}.sql",
            relative_path=Path("models") / f"{model_name}.sql",
            contents=f"MODEL ();\n\n{sql}\n",
            header_values={},
            header_column_locations={},
            output_column_locations={},
            query_sql=sql,
        )
        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
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
