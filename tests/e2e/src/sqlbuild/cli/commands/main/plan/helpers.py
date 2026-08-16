from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.virtual.planner._helpers.planning import (
    build_expected_local_hashes,
    build_expected_version_hashes,
    build_model_fingerprint_metadata_jsons,
)
from sqlbuild.virtual.state._helpers.state_runtime.backend import build_state_backend
from sqlbuild.virtual.state._helpers.state_runtime.config import resolve_state_backend_config
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.main.encoding._encode_state_text import encode_state_text
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    StateBackendConfig,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import ModelVersionStatus, VirtualEnvironmentStatus
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


def build_virtual_plan_project_toml() -> str:
    return (
        'name = "virtual_plan_project"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n\n'
        "[settings]\n"
        "virtual_environments = true\n\n"
        "[connection]\n"
        'database = "warehouse.duckdb"\n\n'
        "[targets.dev]\n"
        'schema = "dev"\n\n'
        "[targets.dev.state]\n"
        'backend = "duckdb"\n'
        'schema = "sqlbuild_state"\n\n'
        "[targets.dev.state.connection]\n"
        'database = "state.duckdb"\n'
    )


def standard_model_version_hashes(*, db_path: Path, model_name: str) -> list[tuple[object, ...]]:
    return query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT version_hash FROM main._sqlbuild_fingerprints "
            f"WHERE node_name = '{model_name}' ORDER BY ts"
        ),
    )


def only_json_model(payload: dict[str, object]) -> dict[str, object]:
    models: list[dict[str, object]] = cast(list[dict[str, object]], payload["models"])
    assert len(models) == 1, payload
    return models[0]


def build_virtual_plan_repo_files(
    *, stg_orders_sql: str, dim_customers_sql: str = "SELECT 1 AS customer_id"
) -> dict[str, str]:
    return {
        "sqlbuild_project.toml": build_virtual_plan_project_toml(),
        "models/stg_orders.sql": f"MODEL ();\n\n{stg_orders_sql}\n",
        "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
        "models/dim_customers.sql": f"MODEL ();\n\n{dim_customers_sql}\n",
    }


def prepare_virtual_run_despite_unchanged_project(
    *,
    tmp_path: Path,
    project_name: str,
    run_despite_unchanged: str,
    data_version_sql: str,
    include_freshness: bool = True,
    source_freshness_type: str = "timestamp",
    warehouse_column_type: str = "TIMESTAMP",
) -> Path:
    freshness_fragment: str = {
        False: "",
        True: (
            "\n"
            "    freshness:\n"
            "      strategy: column\n"
            "      column: order_ts\n"
            f"      type: {source_freshness_type}"
        ),
    }[include_freshness]
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    schema: raw\n"
                "    table: raw_orders"
                f"{freshness_fragment}\n"
            ),
            "models/rolling_orders.sql": (
                f"MODEL (materialized table, run_despite_unchanged {run_despite_unchanged});\n\n"
                'SELECT id, order_ts FROM __source("raw_orders")\n'
            ),
            "models/orders_mart.sql": (
                'MODEL (materialized table);\n\nSELECT id, order_ts FROM __ref("rolling_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "CREATE SCHEMA raw;\n"
            f"CREATE TABLE raw.raw_orders (id INTEGER, order_ts {warehouse_column_type});\n"
            f"INSERT INTO raw.raw_orders VALUES (7, {data_version_sql});"
        ),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    return project_dir


def prepare_python_lifecycle_plan_project(*, tmp_path: Path) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_lifecycle_plan_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_lifecycle_plan_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "loaders/window.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader(\n"
                "    destination='window_orders',\n"
                "    write_strategy='table',\n"
                "    columns=[{'name': 'order_id', 'type': 'INTEGER'}],\n"
                ")\n"
                "def load_window_orders(ctx):\n"
                "    return [{'order_id': 7}]\n"
            ),
            "tasks/prepare.py": (
                "from loaders.window import load_window_orders\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=load_window_orders)\n"
                "def prepare_orders(ctx):\n"
                "    return ctx.result(payload={'order_id': 7})\n"
            ),
            "assets/prepare.py": (
                "from tasks.prepare import prepare_orders\n"
                "from sqlbuild.assets import asset\n\n"
                "@asset(depends_on=prepare_orders)\n"
                "def publish_prepared_orders(ctx):\n"
                "    return ctx.result(\n"
                "        payload=ctx.result_of(node_function=prepare_orders).payload,"
                " materialized=True\n"
                "    )\n"
            ),
            "loaders/raw.py": (
                "from assets.prepare import publish_prepared_orders\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader(depends_on=(publish_prepared_orders,))\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 7}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "tasks/profile.py": (
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    return ctx.result(payload={'rows': 1})\n"
            ),
            "tasks/notify.py": (
                "from tasks.profile import profile_fact_orders\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=profile_fact_orders)\n"
                "def notify_fact_orders(ctx):\n"
                "    return ctx.result("
                "metadata=ctx.result_of(node_function=profile_fact_orders).payload)\n"
            ),
        },
    )


def seed_matching_virtual_refs(
    *, project_dir: Path, source_project_dir: Path | None = None
) -> None:
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    adapter: DuckDbAdapter = DuckDbAdapter()
    effective_source_project_dir: Path = source_project_dir or project_dir
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
                connection=connection,
                schema=config.schema,
                record=ModelVersionRecord(
                    model_name=model_name,
                    version_hash=expected_hashes[model_name],
                    definition_identity_hash=expected_local_hashes[model_name],
                    identity_metadata_hash=expected_hashes[model_name],
                    status=ModelVersionStatus.READY,
                    definition_text_b64=encode_state_text(query_sqls[model_name]),
                    identity_metadata_json_b64=encode_state_text(metadata_jsons[model_name]),
                ),
            )
        backend.upsert_virtual_environment(
            connection=connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name="dev",
                status=VirtualEnvironmentStatus.FINALIZED,
            ),
        )
        backend.replace_virtual_environment_model_refs(
            connection=connection,
            schema=config.schema,
            virtual_environment_name="dev",
            refs=tuple(
                VirtualEnvironmentModelRefRecord(
                    virtual_environment_name="dev",
                    model_name=model_name,
                    version_hash=expected_hashes[model_name],
                )
                for model_name in model_names
            ),
        )
    finally:
        backend.close(connection)
