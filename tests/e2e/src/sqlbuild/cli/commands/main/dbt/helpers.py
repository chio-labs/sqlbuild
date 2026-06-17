from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from shutil import copytree
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtLineageErrorE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import REPO_ROOT

DBT_INTEROP_FIXTURE_DIR: Path = REPO_ROOT / "tests" / "e2e" / "fixtures" / "dbt_interop"


def skip_unless_dbt_is_runnable() -> None:
    """Skip e2e dbt tests when the dbt CLI is unavailable."""

    result: subprocess.CompletedProcess[str] = subprocess.run(
        ("dbt", "--version"),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"dbt CLI is not runnable: {result.stderr or result.stdout}")


def prepare_dbt_interop_project(*, tmp_path: Path) -> Path:
    """Copy the reusable dbt interop fixture and return its SQLBuild project root."""

    root_dir: Path = tmp_path / "dbt_interop"
    copytree(DBT_INTEROP_FIXTURE_DIR, root_dir)
    local_config_path: Path = root_dir / "sqlbuild_project" / "sqlbuild_local.toml"
    if local_config_path.exists():
        local_config_path.unlink()
    db_path: Path = root_dir / "sqlbuild_project" / "dbt_interop.duckdb"
    if db_path.exists():
        db_path.unlink()
    profiles_path: Path = root_dir / "profiles" / "profiles.yml"
    profiles_path.write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n",
        encoding="utf-8",
    )
    return root_dir / "sqlbuild_project"


def compile_dbt_interop_manifest(*, project_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run dbt compile so plain SQLBuild commands can validate dbt refs."""

    dbt_project_dir: Path = project_dir.parent / "dbt_project"
    profiles_dir: Path = project_dir.parent / "profiles"
    target_path: Path = dbt_project_dir / "target"
    return subprocess.run(
        (
            "dbt",
            "compile",
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
            "--target-path",
            target_path.as_posix(),
        ),
        capture_output=True,
        check=False,
        text=True,
    )


def load_json_stdout(stdout: str) -> dict[str, object]:
    """Load JSON command output."""

    payload: object = json.loads(stdout)
    assert isinstance(payload, dict)
    return payload


def assert_dbt_lineage_json_payload(
    *,
    payload: dict[str, object],
    expected_node_ids: tuple[str, ...],
    expected_edges: tuple[tuple[str, str], ...],
    expected_focus: tuple[str, ...],
    expected_direction: str,
    expected_node_metadata: tuple[tuple[str, str, object], ...] = (),
) -> None:
    """Assert stable dbt lineage JSON output."""

    nodes_payload: object = payload["nodes"]
    edges_payload: object = payload["edges"]
    focus_payload: object = payload["focus"]
    assert isinstance(nodes_payload, Sequence)
    assert isinstance(edges_payload, Sequence)
    assert isinstance(focus_payload, Sequence)
    nodes: list[Mapping[str, object]] = [
        cast(Mapping[str, object], node) for node in nodes_payload if isinstance(node, dict)
    ]
    assert [node["id"] for node in nodes] == list(expected_node_ids)
    assert [
        (cast(Mapping[str, object], edge)["from"], cast(Mapping[str, object], edge)["to"])
        for edge in edges_payload
        if isinstance(edge, dict)
    ] == list(expected_edges)
    assert list(focus_payload) == list(expected_focus)
    assert payload["direction"] == expected_direction
    node_by_id: dict[str, Mapping[str, object]] = {str(node["id"]): node for node in nodes}
    for node_id, metadata_key, expected_value in expected_node_metadata:
        assert node_by_id[node_id][metadata_key] == expected_value, (
            node_id,
            metadata_key,
            node_by_id[node_id][metadata_key],
        )


def assert_dbt_column_lineage_json_payload(
    *,
    payload: dict[str, object],
    expected_target: tuple[str, str, str],
    expected_edges: tuple[tuple[str, str], ...],
    expected_direction: str,
    expected_warnings: tuple[str, ...] = (),
) -> None:
    """Assert stable dbt column lineage JSON output."""

    target_payload: object = payload["target"]
    trace_payload: object = payload["trace"]
    metadata_payload: object = payload["metadata"]
    assert isinstance(target_payload, dict)
    assert isinstance(trace_payload, Sequence)
    assert isinstance(metadata_payload, dict)
    target: Mapping[str, object] = cast(Mapping[str, object], target_payload)
    metadata: Mapping[str, object] = cast(Mapping[str, object], metadata_payload)
    assert (
        target["resource_type"],
        target["resource_name"],
        target["column_name"],
    ) == expected_target
    assert [
        (
            _column_payload_id(
                cast(Mapping[str, object], cast(Mapping[str, object], edge)["source"])
            ),
            _column_payload_id(
                cast(Mapping[str, object], cast(Mapping[str, object], edge)["target"])
            ),
        )
        for edge in trace_payload
        if isinstance(edge, dict)
    ] == list(expected_edges)
    assert payload["direction"] == expected_direction
    assert metadata["warnings"] == list(expected_warnings), metadata["warnings"]


def _column_payload_id(column: Mapping[str, object]) -> str:
    return f"{column['resource_name']}:{column['column_name']}"


def remove_dbt_phase11_sqlbuild_models(*, project_dir: Path) -> None:
    """Remove all SQLBuild model files from the focused dbt fixture."""

    model_path: Path
    for model_path in (project_dir / "models").glob("*.sql"):
        model_path.unlink()


def write_dbt_phase11_missing_ref_model(project_dir: Path) -> None:
    """Make dbt compile fail before lineage can load a manifest."""

    (project_dir.parent / "dbt_project" / "models" / "fact_orders.sql").write_text(
        "select order_id from {{ ref('does_not_exist') }}\n",
        encoding="utf-8",
    )


def write_dbt_phase11_invalid_sqlbuild_model(project_dir: Path) -> None:
    """Add a SQLBuild model that only compiles with SQL validation disabled."""

    (project_dir / "models" / "invalid_sql.sql").write_text(
        "MODEL (materialized table);\n\nSELECT FROM\n",
        encoding="utf-8",
    )


def write_dbt_phase11_star_lineage_models(project_dir: Path) -> None:
    """Use SELECT * dbt models to exercise adapter-described source schemas."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    (dbt_models_dir / "stg_orders.sql").write_text(
        "select * from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "fact_orders.sql").write_text(
        "select * from {{ ref('stg_orders') }}\n",
        encoding="utf-8",
    )


def drop_dbt_phase11_orders_source_table(project_dir: Path) -> None:
    """Remove the physical source table while keeping the dbt source definition."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    execute_duckdb(
        db_path=project_dir / "dbt_phase11.duckdb",
        sql="DROP TABLE IF EXISTS main.raw_orders",
    )


def apply_dbt_lineage_error_setup(
    *, project_dir: Path, test_case: DbtLineageErrorE2ETestCase
) -> None:
    """Apply optional setup for a dbt lineage error E2E."""

    if test_case.setup is not None:
        test_case.setup(project_dir)


def query_dbt_phase11_source_freshness_rows(*, project_dir: Path) -> list[tuple[object, ...]]:
    """Return dbt Phase 11 source freshness state rows when the state table exists."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import query_duckdb, table_exists

    db_path: Path = project_dir / "dbt_phase11.duckdb"
    if not table_exists(db_path=db_path, table_name="_sqlbuild_source_freshness"):
        return []
    return query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT source_name, data_version FROM main._sqlbuild_source_freshness "
            "ORDER BY source_name, data_version"
        ),
    )


def query_dbt_phase11_schema_source_freshness_rows(
    *, project_dir: Path, schema: str
) -> list[tuple[object, ...]]:
    """Return dbt Phase 11 source freshness state rows for a specific schema."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import query_duckdb, table_exists

    db_path: Path = project_dir / "dbt_phase11.duckdb"
    if not table_exists(db_path=db_path, table_name="_sqlbuild_source_freshness", schema=schema):
        return []
    return query_duckdb(
        db_path=db_path,
        sql=(
            f"SELECT source_name, data_version FROM {schema}._sqlbuild_source_freshness "
            "ORDER BY source_name, data_version"
        ),
    )


def set_dbt_phase11_sqlbuild_target_schema(*, project_dir: Path, schema: str) -> None:
    """Change the focused Phase 11 SQLBuild target schema."""

    project_file: Path = project_dir / "sqlbuild_project.toml"
    project_file.write_text(
        project_file.read_text(encoding="utf-8").replace('schema = "main"', f'schema = "{schema}"'),
        encoding="utf-8",
    )


def write_dbt_phase11_invalid_downstream_model(*, project_dir: Path) -> None:
    """Make the downstream SQLBuild model fail during warehouse execution."""

    (project_dir / "models" / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT missing_column FROM __dbt_ref("analytics", "fact_orders")\n',
        encoding="utf-8",
    )


def add_dbt_phase11_payments_branch(*, project_dir: Path) -> None:
    """Add a dbt model that depends on orders and payments sources."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    sqlbuild_models_dir: Path = project_dir / "models"
    sources_path: Path = dbt_models_dir / "sources.yml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8")
        + "      - name: payments\n"
        + "        identifier: raw_payments\n"
        + "        loaded_at_field: loaded_at\n"
        + "        freshness:\n"
        + "          error_after: {count: 1, period: day}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "order_payments.sql").write_text(
        "select o.order_id, o.amount as order_amount, p.payment_amount "
        "from {{ source('raw', 'orders') }} o "
        "join {{ source('raw', 'payments') }} p using (order_id)\n",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "payment_summary.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id, payment_amount FROM __dbt_ref("analytics", "order_payments")\n',
        encoding="utf-8",
    )


def add_dbt_phase11_query_filter_branch(*, project_dir: Path) -> None:
    """Add dbt sources that exercise loaded_at_query and freshness filter translation."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    sqlbuild_models_dir: Path = project_dir / "models"
    sources_path: Path = dbt_models_dir / "sources.yml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8")
        + "      - name: query_events\n"
        + "        identifier: raw_query_events\n"
        + "        loaded_at_query: SELECT MAX(loaded_at) AS loaded_at FROM main.raw_query_events\n"
        + "        freshness:\n"
        + "          error_after: {count: 1, period: day}\n"
        + "      - name: filtered_events\n"
        + "        identifier: raw_filtered_events\n"
        + "        loaded_at_field: loaded_at\n"
        + "        freshness:\n"
        + "          error_after: {count: 1, period: day}\n"
        + "          filter: include_in_freshness\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "event_rollup.sql").write_text(
        "select event_id, event_amount from {{ source('raw', 'query_events') }}\n"
        "union all\n"
        "select event_id, event_amount from {{ source('raw', 'filtered_events') }}\n",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "event_summary.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT event_id, event_amount FROM __dbt_ref("analytics", "event_rollup")\n',
        encoding="utf-8",
    )


def prepare_dbt_phase11_project(*, tmp_path: Path, replay_on_change: str | None = None) -> Path:
    """Write a focused dbt interop project for model-planning E2Es."""

    root_dir: Path = tmp_path / "dbt_phase11"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    dbt_seeds_dir: Path = dbt_project_dir / "seeds"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    dbt_models_dir.mkdir(parents=True)
    dbt_seeds_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)

    db_path: Path = sqlbuild_project_dir / "dbt_phase11.duckdb"
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n",
        encoding="utf-8",
    )
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "seed-paths: ['seeds']\n"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    (dbt_seeds_dir / "country_codes.csv").write_text(
        "country_code,country_name\nUS,United States\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "sources.yml").write_text(
        "version: 2\n"
        "sources:\n"
        "  - name: raw\n"
        "    schema: main\n"
        "    tables:\n"
        "      - name: orders\n"
        "        identifier: raw_orders\n"
        "        loaded_at_field: loaded_at\n"
        "        freshness:\n"
        "          error_after: {count: 1, period: day}\n"
        "      - name: customers\n"
        "        identifier: raw_customers\n",
        encoding="utf-8",
    )
    write_dbt_phase11_fact_orders_model(
        project_dir=sqlbuild_project_dir, amount_expression="amount"
    )
    (dbt_models_dir / "stg_orders.sql").write_text(
        "select order_id, customer_id, amount, loaded_at from {{ source('raw', 'orders') }}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "stg_customers.sql").write_text(
        "select customer_id, customer_name from {{ source('raw', 'customers') }}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "dim_customers.sql").write_text(
        "select customer_id, customer_name from {{ ref('stg_customers') }}\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "schema.yml").write_text(
        "version: 2\n"
        "models:\n"
        "  - name: fact_orders\n"
        "    columns:\n"
        "      - name: order_id\n"
        "        tests: [not_null]\n"
        "  - name: dim_customers\n"
        "    columns:\n"
        "      - name: customer_id\n"
        "        tests: [not_null]\n",
        encoding="utf-8",
    )
    replay_line: str = (
        f'replay_on_change = "{replay_on_change}"\n' if replay_on_change is not None else ""
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(
        'name = "dbt_phase11"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        'database = "dbt_phase11.duckdb"\n'
        "[targets.dev]\n"
        'schema = "main"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n'
        f"{replay_line}",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id, amount AS downstream_amount FROM __dbt_ref("analytics", "fact_orders")\n',
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "customer_summary.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT customer_id, customer_name FROM __dbt_ref("analytics", "dim_customers")\n',
        encoding="utf-8",
    )
    seed_dbt_phase11_sources(project_dir=sqlbuild_project_dir, stale_orders=False)
    return sqlbuild_project_dir


def prepare_dbt_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a focused DuckDB dbt reuse_from project with a local prod git ref."""

    root_dir: Path = tmp_path / "dbt_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_reuse_from.duckdb"
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: main\n"
        "    prod:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: prod\n",
        encoding="utf-8",
    )
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    write_dbt_reuse_from_fact_orders_model(project_dir=sqlbuild_project_dir, amount=900)
    (dbt_models_dir / "unrelated_model.sql").write_text(
        "select 77 as unrelated_id\n",
        encoding="utf-8",
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(
        'name = "dbt_reuse_from"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        'database = "dbt_reuse_from.duckdb"\n'
        "[targets.dev]\n"
        'schema = "main"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n'
        "[dbt.reuse_from]\n"
        'git_ref = "prod"\n'
        'generate_schema_name_override = "dbt/macros/prod_generate_schema_name.sql"\n',
        encoding="utf-8",
    )
    (macro_dir / "prod_generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n  prod\n{%- endmacro %}\n",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id, amount AS downstream_amount FROM __dbt_ref("analytics", "fact_orders")\n',
        encoding="utf-8",
    )
    _run_git(args=("init",), cwd=root_dir)
    _run_git(args=("config", "user.email", "sqlbuild@example.invalid"), cwd=root_dir)
    _run_git(args=("config", "user.name", "SQLBuild Test"), cwd=root_dir)
    _run_git(args=("add", "."), cwd=root_dir)
    _run_git(args=("commit", "-m", "prod baseline"), cwd=root_dir)
    _run_git(args=("branch", "prod"), cwd=root_dir)
    subprocess.run(
        (
            "dbt",
            "run",
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
            "--target",
            "prod",
        ),
        capture_output=True,
        check=True,
        text=True,
    )
    write_dbt_reuse_from_fact_orders_model(project_dir=sqlbuild_project_dir, amount=111)
    return sqlbuild_project_dir


def prepare_dbt_seeded_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a focused DuckDB dbt reuse_from project for seeded incremental reuse."""

    root_dir: Path = tmp_path / "dbt_seeded_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_seeded_reuse_from.duckdb"
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: main\n"
        "    prod:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: prod\n",
        encoding="utf-8",
    )
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\nversion: '1.0'\nprofile: analytics\nmodel-paths: ['models']\n",
        encoding="utf-8",
    )
    (dbt_models_dir / "fact_orders.sql").write_text(
        "{{ config(materialized='incremental', "
        "meta={'sqlbuild': {'reuse_cursor': 'event_time'}}) }}\n"
        "select order_id, amount, event_time from main.raw_orders\n"
        "{% if is_incremental() %}\n"
        "where event_time > (select max(event_time) from {{ this }})\n"
        "{% endif %}\n",
        encoding="utf-8",
    )
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id, amount AS downstream_amount FROM __dbt_ref("analytics", "fact_orders")\n',
        encoding="utf-8",
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(
        'name = "dbt_seeded_reuse_from"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        'database = "dbt_seeded_reuse_from.duckdb"\n'
        "[targets.dev]\n"
        'schema = "main"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n'
        "[dbt.reuse_from]\n"
        'git_ref = "prod"\n'
        'generate_schema_name_override = "dbt/macros/prod_generate_schema_name.sql"\n',
        encoding="utf-8",
    )
    (macro_dir / "prod_generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n  prod\n{%- endmacro %}\n",
        encoding="utf-8",
    )
    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE TABLE main.raw_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time"
        ),
    )
    _run_git(args=("init",), cwd=root_dir)
    _run_git(args=("config", "user.email", "sqlbuild@example.invalid"), cwd=root_dir)
    _run_git(args=("config", "user.name", "SQLBuild Test"), cwd=root_dir)
    _run_git(args=("add", "."), cwd=root_dir)
    _run_git(args=("commit", "-m", "prod seeded baseline"), cwd=root_dir)
    _run_git(args=("branch", "prod"), cwd=root_dir)
    subprocess.run(
        (
            "dbt",
            "run",
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
            "--target",
            "prod",
        ),
        capture_output=True,
        check=True,
        text=True,
    )
    execute_duckdb(
        db_path=db_path,
        sql=("INSERT INTO main.raw_orders VALUES (2, 901, TIMESTAMP '2026-01-02')"),
    )
    return sqlbuild_project_dir


def prepare_dbt_multi_node_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a DuckDB dbt reuse_from project with three reusable table models."""

    root_dir: Path = tmp_path / "dbt_multi_node_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_multi_node_reuse_from.duckdb"
    _write_reuse_from_profiles(profiles_dir=profiles_dir, db_path=db_path)
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    model_name: str
    for model_name in ("orders_a", "orders_b", "orders_c"):
        (dbt_models_dir / f"{model_name}.sql").write_text(
            f"select '{model_name}' as model_name, 900 as amount\n",
            encoding="utf-8",
        )
    _write_reuse_from_sqlbuild_project(
        sqlbuild_project_dir=sqlbuild_project_dir,
        project_name="dbt_multi_node_reuse_from",
        database_name="dbt_multi_node_reuse_from.duckdb",
    )
    _write_prod_schema_macro(macro_dir=macro_dir)
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT model_name, amount AS downstream_amount FROM __dbt_ref("analytics", "orders_a")\n'
        "UNION ALL\n"
        'SELECT model_name, amount AS downstream_amount FROM __dbt_ref("analytics", "orders_b")\n'
        "UNION ALL\n"
        'SELECT model_name, amount AS downstream_amount FROM __dbt_ref("analytics", "orders_c")\n',
        encoding="utf-8",
    )
    _initialize_reuse_from_git(root_dir=root_dir)
    _run_dbt(
        args=("run",), dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target="prod"
    )
    for model_name in ("orders_a", "orders_b", "orders_c"):
        (dbt_models_dir / f"{model_name}.sql").write_text(
            f"select '{model_name}' as model_name, 111 as amount\n",
            encoding="utf-8",
        )
    return sqlbuild_project_dir


def prepare_dbt_multi_node_seeded_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a DuckDB dbt reuse_from project with three seeded incremental models."""

    root_dir: Path = tmp_path / "dbt_multi_node_seeded_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    dbt_models_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_multi_node_seeded_reuse_from.duckdb"
    _write_reuse_from_profiles(profiles_dir=profiles_dir, db_path=db_path)
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\nversion: '1.0'\nprofile: analytics\nmodel-paths: ['models']\n",
        encoding="utf-8",
    )
    model_name: str
    for model_name in ("orders_a", "orders_b", "orders_c"):
        (dbt_models_dir / f"{model_name}.sql").write_text(
            "{{ config(materialized='incremental', "
            "meta={'sqlbuild': {'reuse_cursor': 'event_time'}}) }}\n"
            f"select model_name, order_id, amount, event_time from main.raw_{model_name}\n"
            "{% if is_incremental() %}\n"
            "where event_time > (select max(event_time) from {{ this }})\n"
            "{% endif %}\n",
            encoding="utf-8",
        )
    _write_reuse_from_sqlbuild_project(
        sqlbuild_project_dir=sqlbuild_project_dir,
        project_name="dbt_multi_node_seeded_reuse_from",
        database_name="dbt_multi_node_seeded_reuse_from.duckdb",
    )
    _write_prod_schema_macro(macro_dir=macro_dir)
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        "SELECT model_name, order_id, amount AS downstream_amount "
        'FROM __dbt_ref("analytics", "orders_a")\n'
        "UNION ALL\n"
        "SELECT model_name, order_id, amount AS downstream_amount "
        'FROM __dbt_ref("analytics", "orders_b")\n'
        "UNION ALL\n"
        "SELECT model_name, order_id, amount AS downstream_amount "
        'FROM __dbt_ref("analytics", "orders_c")\n',
        encoding="utf-8",
    )
    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    seed_sql_parts: list[str] = []
    for model_name in ("orders_a", "orders_b", "orders_c"):
        seed_sql_parts.append(
            f"CREATE TABLE main.raw_{model_name} AS "
            f"SELECT '{model_name}' AS model_name, 1 AS order_id, 900 AS amount, "
            "TIMESTAMP '2026-01-01' AS event_time"
        )
    execute_duckdb(db_path=db_path, sql="; ".join(seed_sql_parts))
    _initialize_reuse_from_git(root_dir=root_dir)
    _run_dbt(
        args=("run",), dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target="prod"
    )
    for model_name in ("orders_a", "orders_b", "orders_c"):
        execute_duckdb(
            db_path=db_path,
            sql=(
                f"INSERT INTO main.raw_{model_name} VALUES "
                f"('{model_name}', 2, 901, TIMESTAMP '2026-01-02')"
            ),
        )
    return sqlbuild_project_dir


def prepare_dbt_snapshot_seeded_reuse_from_project(*, tmp_path: Path) -> Path:
    """Write a DuckDB dbt reuse_from project with a seeded dbt snapshot."""

    root_dir: Path = tmp_path / "dbt_snapshot_seeded_reuse_from"
    dbt_project_dir: Path = root_dir / "dbt_project"
    profiles_dir: Path = root_dir / "profiles"
    sqlbuild_project_dir: Path = root_dir / "sqlbuild_project"
    snapshots_dir: Path = dbt_project_dir / "snapshots"
    sqlbuild_models_dir: Path = sqlbuild_project_dir / "models"
    macro_dir: Path = sqlbuild_project_dir / "dbt" / "macros"
    snapshots_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_models_dir.mkdir(parents=True)
    macro_dir.mkdir(parents=True)
    db_path: Path = sqlbuild_project_dir / "dbt_snapshot_seeded_reuse_from.duckdb"
    _write_reuse_from_profiles(profiles_dir=profiles_dir, db_path=db_path)
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "snapshot-paths: ['snapshots']\n",
        encoding="utf-8",
    )
    _write_dbt_orders_snapshot(snapshots_dir=snapshots_dir, target_schema="prod")
    _write_reuse_from_sqlbuild_project(
        sqlbuild_project_dir=sqlbuild_project_dir,
        project_name="dbt_snapshot_seeded_reuse_from",
        database_name="dbt_snapshot_seeded_reuse_from.duckdb",
    )
    _write_prod_schema_macro(macro_dir=macro_dir)
    (sqlbuild_models_dir / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        "SELECT order_id, amount AS downstream_amount "
        'FROM __dbt_ref("analytics", "orders_snapshot") '
        "WHERE dbt_valid_to IS NULL\n",
        encoding="utf-8",
    )
    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE TABLE main.raw_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time"
        ),
    )
    _initialize_reuse_from_git(root_dir=root_dir)
    _run_dbt(
        args=("snapshot",),
        dbt_project_dir=dbt_project_dir,
        profiles_dir=profiles_dir,
        target="prod",
    )
    _write_dbt_orders_snapshot(snapshots_dir=snapshots_dir, target_schema="main")
    execute_duckdb(
        db_path=db_path,
        sql="INSERT INTO main.raw_orders VALUES (2, 901, TIMESTAMP '2026-01-02')",
    )
    return sqlbuild_project_dir


def _write_reuse_from_profiles(*, profiles_dir: Path, db_path: Path) -> None:
    profiles_dir.joinpath("profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: main\n"
        "    prod:\n"
        "      type: duckdb\n"
        f"      path: '{db_path.as_posix()}'\n"
        "      schema: prod\n",
        encoding="utf-8",
    )


def _write_reuse_from_sqlbuild_project(
    *, sqlbuild_project_dir: Path, project_name: str, database_name: str
) -> None:
    sqlbuild_project_dir.joinpath("sqlbuild_project.toml").write_text(
        f'name = "{project_name}"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        f'database = "{database_name}"\n'
        "[targets.dev]\n"
        'schema = "main"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n'
        "[dbt.reuse_from]\n"
        'git_ref = "prod"\n'
        'generate_schema_name_override = "dbt/macros/prod_generate_schema_name.sql"\n',
        encoding="utf-8",
    )


def _write_prod_schema_macro(*, macro_dir: Path) -> None:
    macro_dir.joinpath("prod_generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n  prod\n{%- endmacro %}\n",
        encoding="utf-8",
    )


def _write_dbt_orders_snapshot(*, snapshots_dir: Path, target_schema: str) -> None:
    snapshots_dir.joinpath("orders_snapshot.sql").write_text(
        "{% snapshot orders_snapshot %}\n"
        "{{ config(\n"
        f"  target_schema='{target_schema}',\n"
        "  unique_key='order_id',\n"
        "  strategy='timestamp',\n"
        "  updated_at='event_time',\n"
        "  meta={'sqlbuild': {'reuse_cursor': 'event_time'}}\n"
        ") }}\n"
        "select order_id, amount, event_time from main.raw_orders\n"
        "{% endsnapshot %}\n",
        encoding="utf-8",
    )


def _initialize_reuse_from_git(*, root_dir: Path) -> None:
    _run_git(args=("init",), cwd=root_dir)
    _run_git(args=("config", "user.email", "sqlbuild@example.invalid"), cwd=root_dir)
    _run_git(args=("config", "user.name", "SQLBuild Test"), cwd=root_dir)
    _run_git(args=("add", "."), cwd=root_dir)
    _run_git(args=("commit", "-m", "prod baseline"), cwd=root_dir)
    _run_git(args=("branch", "prod"), cwd=root_dir)


def _run_dbt(
    *, args: tuple[str, ...], dbt_project_dir: Path, profiles_dir: Path, target: str
) -> None:
    subprocess.run(
        (
            "dbt",
            *args,
            "--project-dir",
            dbt_project_dir.as_posix(),
            "--profiles-dir",
            profiles_dir.as_posix(),
            "--target",
            target,
        ),
        capture_output=True,
        check=True,
        text=True,
    )


def write_dbt_reuse_from_fact_orders_model(*, project_dir: Path, amount: int) -> None:
    """Write the mutable dbt model used by reuse_from E2Es."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    (dbt_models_dir / "fact_orders.sql").write_text(
        f"select 1 as order_id, {amount} as amount\n",
        encoding="utf-8",
    )


def _run_git(*, args: tuple[str, ...], cwd: Path) -> None:
    subprocess.run(("git", *args), cwd=cwd, capture_output=True, check=True, text=True)


def add_dbt_phase11_sqlbuild_function_branch(*, project_dir: Path) -> None:
    """Add a SQLBuild UDF branch downstream of the dbt orders model."""

    functions_dir: Path = project_dir / "functions" / "sql"
    models_dir: Path = project_dir / "models"
    functions_dir.mkdir(parents=True, exist_ok=True)
    (functions_dir / "is_large_amount.sql").write_text(
        "FUNCTION (\n  arguments (amount INTEGER),\n  returns BOOLEAN,\n);\n\namount > 50\n",
        encoding="utf-8",
    )
    (models_dir / "amount_quality.sql").write_text(
        "MODEL (materialized table);\n\n"
        "SELECT\n"
        "  order_id,\n"
        '  __udf("is_large_amount")(downstream_amount) AS is_large_amount\n'
        'FROM __ref("downstream_orders")\n',
        encoding="utf-8",
    )


def write_dbt_phase11_fact_orders_model(*, project_dir: Path, amount_expression: str) -> None:
    """Write the mutable dbt fact_orders model used by Phase 11 E2Es."""

    dbt_models_dir: Path = project_dir.parent / "dbt_project" / "models"
    (dbt_models_dir / "fact_orders.sql").write_text(
        "select order_id, customer_id, "
        f"{amount_expression} as amount from {{{{ ref('stg_orders') }}}}\n",
        encoding="utf-8",
    )


def seed_dbt_phase11_sources(*, project_dir: Path, stale_orders: bool) -> None:
    """Create raw DuckDB tables for the focused Phase 11 dbt project."""

    from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import execute_duckdb

    loaded_at: str = "2000-01-01 00:00:00" if stale_orders else "2999-01-01 00:00:00"
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_orders AS "
            "SELECT 1 AS order_id, 10 AS customer_id, 100 AS amount, "
            f"TIMESTAMP '{loaded_at}' AS loaded_at"
        ),
    )
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 10 AS customer_id, 'Ada' AS customer_name"
        ),
    )
