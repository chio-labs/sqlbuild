from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.virtual.planner.helpers.planning import (
    build_expected_local_hashes,
    build_expected_version_hashes,
    build_model_fingerprint_metadata_jsons,
)
from sqlbuild.virtual.shared.helpers.encoding import encode_state_text
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.helpers.backend import build_state_backend
from sqlbuild.virtual.state.helpers.config import resolve_state_backend_config
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    StateBackendConfig,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import ModelVersionStatus, VirtualEnvironmentStatus


def build_virtual_plan_project_toml() -> str:
    return (
        'name = "virtual_plan_project"\n'
        'adapter = "duckdb"\n'
        'environment_mode = "virtual"\n'
        'default_environment = "dev"\n\n'
        "[connection]\n"
        'database = "warehouse.duckdb"\n\n'
        "[environments.dev]\n"
        'schema = "dev"\n\n'
        "[environments.dev.state]\n"
        'backend = "duckdb"\n'
        'schema = "sqlbuild_state"\n\n'
        "[environments.dev.state.connection]\n"
        'database = "state.duckdb"\n'
    )


def build_virtual_plan_repo_files(
    *, stg_orders_sql: str, dim_customers_sql: str = "SELECT 1 AS customer_id"
) -> dict[str, str]:
    return {
        "sqlbuild_project.toml": build_virtual_plan_project_toml(),
        "models/stg_orders.sql": f"MODEL ();\n\n{stg_orders_sql}\n",
        "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
        "models/dim_customers.sql": f"MODEL ();\n\n{dim_customers_sql}\n",
    }


def seed_matching_virtual_refs(
    *, project_dir: Path, source_project_dir: Path | None = None
) -> None:
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    adapter: DuckDbAdapter = DuckDbAdapter()
    effective_source_project_dir: Path = (
        source_project_dir if source_project_dir is not None else project_dir
    )
    source_discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_source_project_dir
    )
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=source_discovered_inputs,
        adapter=adapter,
    )
    expected_local_hashes: dict[str, str] = build_expected_local_hashes(graph=graph)
    expected_hashes: dict[str, str] = build_expected_version_hashes(
        graph=graph,
        expected_local_hashes=expected_local_hashes,
    )
    metadata_jsons: dict[str, str] = build_model_fingerprint_metadata_jsons(graph=graph)
    config: StateBackendConfig = resolve_state_backend_config(
        discovered_inputs=discovered_inputs, project_dir=project_dir
    )
    backend: StateBackend = build_state_backend(config.backend)
    connection: Any = backend.connect(config.connection)
    try:
        query_sqls: dict[str, str] = {model.name: model.query_sql for model in graph.project.models}
        model_names: tuple[str, ...] = tuple(model.name for model in graph.project.models)
        model_name: str
        for model_name in model_names:
            backend.upsert_model_version(
                connection,
                schema=config.schema,
                record=ModelVersionRecord(
                    model_name=model_name,
                    version_hash=expected_hashes[model_name],
                    data_hash=expected_local_hashes[model_name],
                    metadata_hash=expected_hashes[model_name],
                    status=ModelVersionStatus.READY,
                    fingerprint_query_sql_b64=encode_state_text(query_sqls[model_name]),
                    fingerprint_metadata_json_b64=encode_state_text(metadata_jsons[model_name]),
                ),
            )
        backend.upsert_virtual_environment(
            connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name="dev",
                status=VirtualEnvironmentStatus.FINALIZED,
            ),
        )
        backend.replace_virtual_environment_refs(
            connection,
            schema=config.schema,
            virtual_environment_name="dev",
            refs=tuple(
                VirtualEnvironmentRefRecord(
                    virtual_environment_name="dev",
                    model_name=model_name,
                    version_hash=expected_hashes[model_name],
                )
                for model_name in model_names
            ),
        )
    finally:
        backend.close(connection)
