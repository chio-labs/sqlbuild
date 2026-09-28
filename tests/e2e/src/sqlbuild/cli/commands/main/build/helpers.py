from __future__ import annotations

import json
import subprocess
from pathlib import Path
from textwrap import dedent

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DeferCloneBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


def run_replay_command(
    *, command: tuple[str, ...], project_dir: Path
) -> subprocess.CompletedProcess[str]:
    """Run a successful replay lifecycle command and retain its output."""
    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", *command), project_dir=project_dir
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def replay_order_rows(*, db_path: Path, table: str) -> list[tuple[object, ...]]:
    """Read complete replay results in deterministic order."""
    return query_duckdb(
        db_path=db_path, sql=f"SELECT order_date, amount_cents FROM main.{table} ORDER BY 1"
    )


def capped_microbatch_project_files(
    *, limit_action: str, project_limit: str = ""
) -> dict[str, str]:
    """Build a direct DuckDB project with one capped producer and plain consumer."""

    return {
        "sqlbuild_project.toml": dedent(
            f"""
            name = "capped_microbatch"
            adapter = "duckdb"

            [connection]
            database = "regression.duckdb"
            {project_limit}
            """
        ).strip()
        + "\n",
        "sources/raw.yml": dedent(
            """
            sources:
              - name: raw_events
                schema: main
                table: raw_events
            """
        ).strip()
        + "\n",
        "models/capped_events.sql": dedent(
            f"""
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
              microbatch_strategy watermark,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain day,
              cursor_start '2026-01-01',
              cursor_end '2026-01-06',
              cursor_watermark_mode all,
              cursor_inputs (
                raw_events (column event_time, roles [filter, watermark]),
              ),
              batch_size 1d,
              lookback 1d,
              microbatch_limit (
                max_batches 3,
                action {limit_action},
              ),
            );
            SELECT id, event_time
            FROM __source("raw_events")
            """
        ).strip()
        + "\n",
        "models/downstream_events.sql": dedent(
            """
            MODEL (materialized view);
            SELECT id, event_time
            FROM __ref("capped_events")
            """
        ).strip()
        + "\n",
    }


def capped_watermark_consumer_project_files(*, limit_action: str) -> dict[str, str]:
    """Build an invalid project whose watermark consumer reads a capped producer."""

    repo_files: dict[str, str] = capped_microbatch_project_files(limit_action=limit_action)
    repo_files["models/downstream_events.sql"] = (
        dedent(
            """
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
              microbatch_strategy watermark,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain day,
              cursor_start '2026-01-01',
              cursor_watermark_mode all,
              cursor_inputs (
                capped_events (column event_time, roles [filter, watermark]),
              ),
              batch_size 1d,
              lookback 1d,
            );
            SELECT id, event_time
            FROM __ref("capped_events")
            """
        ).strip()
        + "\n"
    )
    return repo_files


def prepare_defer_clone_project(
    *,
    tmp_path: Path,
    project_name: str,
    upstream_sql: str,
    downstream_sql: str,
) -> Path:
    """Write a direct-mode project with clone policies for defer-clone E2Es."""

    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": dedent(
                f"""
                name = "{project_name}"
                adapter = "duckdb"
                default_target = "dev"

                [connection]
                database = "warehouse.duckdb"

                [targets.prod]
                schema = "prod"

                [targets.prod.clone]
                allow_as_clone_origin = true

                [targets.dev]
                schema = "dev"

                [targets.dev.clone]
                allow_as_clone_destination = true
                """
            ).strip()
            + "\n",
            "models/upstream.sql": upstream_sql,
            "models/downstream.sql": downstream_sql,
        },
    )


def assert_defer_clone_build_case(*, tmp_path: Path, test_case: DeferCloneBuildE2ETestCase) -> None:
    """Run and assert one direct-mode defer-clone E2E case."""

    project_dir: Path = prepare_defer_clone_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        upstream_sql=test_case.initial_upstream_sql,
        downstream_sql=test_case.downstream_sql,
    )
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.prod_build_command,
        project_dir=project_dir,
    )
    assert prod_result.returncode == 0, prod_result.stderr or prod_result.stdout
    project_config_path: Path = project_dir / "sqlbuild_project.toml"
    project_config_path.write_text(
        project_config_path.read_text(encoding="utf-8").replace(
            '[targets.prod]\nschema = "prod"',
            '[targets.prod]\nschema = "prod"\n\n[targets.prod.connection]\n'
            'database = "${ENV:SQLBUILD_TEST_UNUSED_DEFER_ORIGIN_DATABASE}"',
        ),
        encoding="utf-8",
    )
    (project_dir / "models" / "upstream.sql").write_text(
        test_case.changed_upstream_sql,
        encoding="utf-8",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.dev_build_command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_stdout_fragments:
        assert unexpected_fragment not in result.stdout
    db_path: Path = project_dir / "warehouse.duckdb"
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT id, label FROM prod.upstream ORDER BY id",
    ) == list(test_case.expected_prod_upstream_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT id, label FROM dev.upstream ORDER BY id",
    ) == list(test_case.expected_dev_upstream_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT id, label FROM dev.downstream ORDER BY id",
    ) == list(test_case.expected_dev_downstream_rows)
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_type, node_name FROM dev._sqlbuild_fingerprints "
            "WHERE node_type = 'model' ORDER BY node_name"
        ),
    ) == list(test_case.expected_fingerprint_rows)


def prepare_build_test_audit_flag_project(*, tmp_path: Path, project_name: str) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": dedent(
                f"""
                name = "{project_name}"
                adapter = "duckdb"

                [connection]
                database = "warehouse.duckdb"
                """
            ).strip()
            + "\n",
            "models/orders.sql": dedent(
                """
                MODEL (
                  materialized table,
                  columns (order_id (audits [not_null])),
                );

                SELECT 1 AS order_id
                """
            ).strip()
            + "\n",
            "tests/unit/test_orders.sql": dedent(
                """
                TEST();

                WITH
                __ref__orders AS (SELECT 1 AS order_id),
                __expected__orders AS (SELECT 1 AS order_id)
                SELECT 1
                """
            ).strip()
            + "\n",
        },
    )


def build_freshness_error_branch_source_yml(
    *,
    order_id: int,
    customer_id: int,
    order_freshness_query: str,
    customer_freshness_query: str,
) -> str:
    return (
        dedent(
            f"""
        sources:
          - name: raw_orders
            expression: SELECT {order_id} AS order_id
            freshness:
              strategy: sql
              type: timestamp
              query: {order_freshness_query}
              age_policy:
                error_after: 1h
          - name: raw_customers
            expression: SELECT {customer_id} AS customer_id
            freshness:
              strategy: sql
              type: timestamp
              query: {customer_freshness_query}
              age_policy:
                error_after: 1h
        """
        ).strip()
        + "\n"
    )


def replay_microbatch_model_sql(*, value_expression: str, replay_policy: str = "bounded-2h") -> str:
    """Build a replay-on-change microbatch model used by lifecycle E2E tests."""

    return (
        dedent(
            f"""
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
              microbatch_strategy watermark,
              cursor_watermark_mode all,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain hour,
              cursor_inputs (
                raw_events (column event_time, roles [filter, watermark]),
              ),
              batch_size 1h,
              batch_concurrency 2,
              replay_on_change {replay_policy},
            );

            SELECT id, event_time, {value_expression} AS value
            FROM __source("raw_events")
            WHERE event_time >= __cursor_start()
              AND event_time < __cursor_end()
            """
        ).strip()
        + "\n"
    )


def direct_microbatch_project_toml(
    *, project_name: str, database_name: str, settings_toml: str
) -> str:
    """Build a direct DuckDB project config for microbatch lifecycle E2Es."""

    return (
        f'name = "{project_name}"\n'
        'adapter = "duckdb"\n\n'
        "[connection]\n"
        f'database = "{database_name}"\n'
        f"{settings_toml}"
    )


def raw_events_source_yml() -> str:
    """Return the canonical raw-events source declaration."""

    return "sources:\n  - name: raw_events\n    schema: main\n    table: raw_events\n"


def timestamp_microbatch_model_sql(
    *,
    value_expression: str,
    batch_concurrency: int,
    replay_policy: str,
    extra_config: str = "",
) -> str:
    """Build a timestamp delete/insert microbatch model for lifecycle E2Es."""

    return (
        dedent(
            f"""
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
              microbatch_strategy watermark,
              cursor_watermark_mode all,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain hour,
              cursor_inputs (
                raw_events (column event_time, roles [filter, watermark]),
              ),
              batch_size 1h,
              batch_concurrency {batch_concurrency},
              replay_on_change {replay_policy},
              {extra_config}
            );

            SELECT id, event_time, {value_expression} AS value
            FROM __source("raw_events")
            WHERE event_time >= __cursor_start()
              AND event_time < __cursor_end()
            """
        ).strip()
        + "\n"
    )


def prepare_replay_microbatch_project(
    *, tmp_path: Path, project_name: str, database_name: str, replay_policy: str
) -> tuple[Path, Path]:
    """Prepare a direct concurrent replay lifecycle project."""

    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": direct_microbatch_project_toml(
                project_name=project_name,
                database_name=database_name,
                settings_toml=("\n[settings]\nconcurrency = 3\nmicrobatch_concurrency = true\n"),
            ),
            "sources/raw.yml": raw_events_source_yml(),
            "models/orders.sql": timestamp_microbatch_model_sql(
                value_expression="CAST(payload AS INTEGER)",
                batch_concurrency=3,
                replay_policy=replay_policy,
            ),
        },
    )
    return project_dir, project_dir / database_name


def dropped_incremental_project_files(*, incremental_strategy: str) -> dict[str, str]:
    """Return a DuckDB project with one timestamp-cursor incremental order model."""

    return {
        "sqlbuild_project.toml": (
            'name = "dropped_orders"\nadapter = "duckdb"\n\n'
            '[connection]\ndatabase = "dropped_orders.duckdb"\n'
        ),
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "models/orders.sql": (
            "MODEL (\n"
            "  materialized incremental,\n"
            f"  incremental_strategy {incremental_strategy},\n"
            "  unique_key id,\n"
            "  cursor ordered_at,\n"
            "  cursor_type timestamp,\n"
            "  cursor_grain day,\n"
            "  cursor_start '2026-01-02',\n"
            ");\n\n"
            'SELECT id, ordered_at FROM __source("raw_orders")\n'
        ),
    }


ATTACHED_AUDIT_GATE_DATABASE: str = "gate_shop.duckdb"
_GATE_AUDIT_TEMPLATE: str = (
    "AUDIT ();\n\n"
    "SELECT s.code FROM @relation s\n"
    "LEFT JOIN {read} a USING (code)\n"
    "WHERE a.code IS NULL\n"
)
_GATE_TARGET_FILES: dict[str, dict[str, str]] = {
    "model": {
        "models/orders.sql": (
            "MODEL (materialized table, audits [code_check (severity error)]);\n\n"
            "SELECT '{code}' AS code\n"
        ),
        "models/order_summary.sql": (
            'MODEL (materialized table);\n\nSELECT code FROM __ref("orders")\n'
        ),
    },
    "source": {
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            "    audits:\n      - code_check:\n          severity: error\n"
        ),
        "models/staged_orders.sql": (
            'MODEL (materialized table);\n\nSELECT code FROM __source("raw_orders")\n'
        ),
    },
    "seed": {
        "seeds/order_codes.yml": (
            "seeds:\n  - name: order_codes\n    columns:\n      - name: code\n"
            "        type: VARCHAR\n    audits:\n      - code_check:\n          severity: error\n"
        ),
        "seeds/order_codes.csv": "code\n{code}\n",
        "models/coded_orders.sql": (
            'MODEL (materialized table);\n\nSELECT code FROM __seed("order_codes")\n'
        ),
    },
}
_GATE_PRE_EXISTING_TABLES: dict[str, tuple[str, ...]] = {
    "model": ("CREATE TABLE main.orders AS SELECT 'previous' AS code",),
    "source": ("CREATE TABLE main.raw_orders AS SELECT '{code}' AS code",),
    "seed": (),
}


def prepare_attached_audit_gate_project(
    *, tmp_path: Path, target_kind: str, order_code: str, read: str = '__ref("valid_codes")'
) -> Path:
    """Write a project whose code_check audit on one target reads the valid_codes model."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": (
            'name = "gate_shop"\nadapter = "duckdb"\n\n'
            f'[connection]\ndatabase = "{ATTACHED_AUDIT_GATE_DATABASE}"\n'
        ),
        "audits/generic/code_check.sql": _GATE_AUDIT_TEMPLATE.format(read=read),
        "models/valid_codes.sql": (
            "MODEL (materialized table);\n\nSELECT code FROM (VALUES ('A'), ('B')) AS valid(code)\n"
        ),
    }
    files.update(
        {
            path: contents.replace("{code}", order_code)
            for path, contents in _GATE_TARGET_FILES[target_kind].items()
        }
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="gate_shop", repo_files=files
    )
    statement: str
    for statement in _GATE_PRE_EXISTING_TABLES[target_kind]:
        execute_duckdb(
            db_path=project_dir / ATTACHED_AUDIT_GATE_DATABASE,
            sql=statement.replace("{code}", order_code),
        )
    return project_dir


def prepare_nested_source_gate_project(*, tmp_path: Path, raw_code: str) -> Path:
    """Write a project whose model audit reads a source that has an audit reading a model."""

    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="gate_shop",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "gate_shop"\nadapter = "duckdb"\n\n'
                f'[connection]\ndatabase = "{ATTACHED_AUDIT_GATE_DATABASE}"\n'
            ),
            "sources/raw.yml": (
                "sources:\n  - name: raw_codes\n    schema: main\n    table: raw_codes\n"
                "    audits:\n      - source_check:\n          severity: error\n"
            ),
            "audits/generic/source_check.sql": _GATE_AUDIT_TEMPLATE.format(
                read='__ref("valid_codes")'
            ),
            "audits/generic/order_check.sql": _GATE_AUDIT_TEMPLATE.format(
                read='__source("raw_codes")'
            ),
            "models/orders.sql": (
                "MODEL (materialized table, audits [order_check (severity error)]);\n\n"
                "SELECT 'A' AS code\n"
            ),
            "models/valid_codes.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT code FROM (VALUES ('A'), ('B')) AS valid(code)\n"
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / ATTACHED_AUDIT_GATE_DATABASE,
        sql=f"CREATE TABLE main.raw_codes AS SELECT * FROM (VALUES ('A'), ('{raw_code}')) t(code)",
    )
    return project_dir


def build_check_outcomes(stdout: str) -> dict[tuple[object, object], tuple[object, object]]:
    """Map (check name, asset) to (attachment kind, status) from build JSON output."""

    return {
        (check["name"], check.get("asset_name")): (check["attachment_kind"], check["status"])
        for check in json.loads(stdout)["checks"]
    }


def build_asset_names(stdout: str) -> tuple[str, ...]:
    """Return the asset names reported by build JSON output."""

    return tuple(asset["name"] for asset in json.loads(stdout)["assets"])


AUDIT_ERROR_DATABASE: str = "error_shop.duckdb"
_BROKEN_AUDIT: str = (
    "AUDIT ();\n\nSELECT r.* FROM @relation r JOIN main.missing_lookup m ON r.code = m.code\n"
)
_AUDIT_ERROR_TARGET_FILES: dict[str, dict[str, str]] = {
    "source": {
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            "    audits:\n      - broken_check:\n          severity: {severity}\n"
        ),
        "audits/generic/broken_check.sql": _BROKEN_AUDIT,
        "models/staged_orders.sql": (
            'MODEL (materialized table);\n\nSELECT code FROM __source("raw_orders")\n'
        ),
    },
    "seed": {
        "seeds/order_codes.yml": (
            "seeds:\n  - name: order_codes\n    columns:\n      - name: code\n"
            "        type: VARCHAR\n    audits:\n      - broken_check:\n"
            "          severity: {severity}\n"
        ),
        "seeds/order_codes.csv": "code\nA\n",
        "audits/generic/broken_check.sql": _BROKEN_AUDIT,
        "models/coded_orders.sql": (
            'MODEL (materialized table);\n\nSELECT code FROM __seed("order_codes")\n'
        ),
    },
    "end": {
        "models/orders.sql": "MODEL (materialized table);\n\nSELECT 'A' AS code\n",
        "models/customers.sql": "MODEL (materialized table);\n\nSELECT 'A' AS code\n",
        "audits/singular/broken_check.sql": (
            "AUDIT (severity {severity});\n\n"
            'SELECT o.code FROM __ref("orders") o JOIN __ref("customers") c USING (code)\n'
            "JOIN main.missing_lookup m USING (code)\n"
        ),
    },
}


def prepare_audit_error_project(*, tmp_path: Path, audit_kind: str, severity: str) -> Path:
    """Write a project whose broken_check audit reads a relation that does not exist."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": (
            'name = "error_shop"\nadapter = "duckdb"\n\n'
            f'[connection]\ndatabase = "{AUDIT_ERROR_DATABASE}"\n'
        ),
    }
    files.update(
        {
            path: contents.replace("{severity}", severity)
            for path, contents in _AUDIT_ERROR_TARGET_FILES[audit_kind].items()
        }
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="error_shop", repo_files=files
    )
    execute_duckdb(
        db_path=project_dir / AUDIT_ERROR_DATABASE,
        sql="CREATE TABLE main.raw_orders AS SELECT 'A' AS code",
    )
    return project_dir


def audit_check_by_name(*, stdout: str, name: str) -> dict[str, object]:
    """Return the build JSON check with the given name."""

    return {check["name"]: check for check in json.loads(stdout)["checks"]}[name]


def build_asset_statuses(stdout: str) -> dict[str, str]:
    """Map asset names to their status in build JSON output."""

    return {asset["name"]: asset["status"] for asset in json.loads(stdout)["assets"]}


def prepare_audit_read_plan_project(*, tmp_path: Path) -> Path:
    """Write a project whose stg_orders column audit reads a seed its SQL does not read."""

    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="plan_shop",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "plan_shop"\nadapter = "duckdb"\n\n'
                '[connection]\ndatabase = "plan_shop.duckdb"\n'
            ),
            "seeds/waffle_types.yml": (
                "seeds:\n  - name: waffle_types\n    columns:\n"
                "      - name: waffle_type_id\n        type: INTEGER\n"
            ),
            "seeds/waffle_types.csv": "waffle_type_id\n1\n",
            "models/stg_orders.sql": (
                "MODEL (\n  materialized table,\n  columns (\n    waffle_type_id (\n"
                '      audits [relationships (to __seed("waffle_types"), field waffle_type_id)],\n'
                "    ),\n  ),\n);\n\nSELECT 1 AS waffle_type_id\n"
            ),
        },
    )


EXPLICIT_REFERENCE_MODELS: str = "models/sales"
EXPLICIT_REFERENCE_MACRO_PATH: str = "models/sales/_sqlbuild/_macros/unions.py"
EXPLICIT_REFERENCE_HOOK_PATH: str = "models/sales/_sqlbuild/_hooks/python/lookups.py"
EXPLICIT_REFERENCE_MACROS: str = (
    "def union_all(relations):\n"
    "    return ' UNION ALL '.join(\n"
    "        f'SELECT order_id, amount FROM {relation}' for relation in relations\n"
    "    )\n"
)
EXPLICIT_REFERENCE_HOOKS: str = (
    "from sqlbuild.hooks import hook\n"
    "from sqlbuild.refs import model\n\n\n"
    '@hook(reads=model("stg_customers"))\n'
    "def record_customers(ctx):\n"
    '    customers = ctx.relation(model("stg_customers"))\n'
    "    ctx.execute_sql(\n"
    '        f"CREATE OR REPLACE TABLE customer_counts AS SELECT count(*) AS n FROM {customers}"\n'
    "    )\n"
)


def explicit_reference_project_files(
    *, overrides: dict[str, str], enforce_explicit: bool = True
) -> dict[str, str]:
    """Return a DuckDB project using typed macro references and a hook with declared reads."""

    references: str = f"\n[references]\nenforce_explicit = {str(enforce_explicit).lower()}\n"
    return {
        "sqlbuild_project.toml": (
            'name = "explicit_refs"\nadapter = "duckdb"\n\n'
            '[connection]\ndatabase = "warehouse.duckdb"\n' + references
        ),
        f"{EXPLICIT_REFERENCE_MODELS}/stg_orders_eu.sql": (
            "MODEL (materialized table);\nSELECT 1 AS order_id, 10 AS amount\n"
        ),
        f"{EXPLICIT_REFERENCE_MODELS}/stg_orders_us.sql": (
            "MODEL (materialized table);\nSELECT 2 AS order_id, 20 AS amount\n"
        ),
        f"{EXPLICIT_REFERENCE_MODELS}/stg_customers.sql": (
            "MODEL (materialized table);\nSELECT 1 AS customer_id\n"
        ),
        f"{EXPLICIT_REFERENCE_MODELS}/all_orders.sql": (
            "MODEL (materialized table);\n"
            '@union_all([__ref("stg_orders_eu"), __ref("stg_orders_us")])\n'
        ),
        f"{EXPLICIT_REFERENCE_MODELS}/orders_summary.sql": (
            'MODEL (materialized table, post_hooks [python("record_customers")]);\n'
            'SELECT count(*) AS order_count FROM __ref("all_orders")\n'
        ),
        EXPLICIT_REFERENCE_MACRO_PATH: EXPLICIT_REFERENCE_MACROS,
        EXPLICIT_REFERENCE_HOOK_PATH: EXPLICIT_REFERENCE_HOOKS,
    } | overrides


def explicit_reference_literal_loader(*, table: str) -> str:
    """Return loaders ``raw_regions`` and ``raw_customers``; the latter queries ``table``."""

    return (
        "from sqlbuild.loaders import loader\n\n\n"
        "@loader\n"
        "def raw_regions(ctx):\n"
        "    return [{'id': 1}]\n\n\n"
        "@loader\n"
        "def raw_customers(ctx):\n"
        f'    ctx.query("SELECT count(*) FROM {table}")\n'
        "    return [{'id': 1}]\n"
    )


PYTHON_NODE_SELECTION_DATABASE: str = "warehouse.duckdb"


def _counting_python_node(*, decorator: str, name: str, ref: str, returned: str) -> str:
    return (
        f"@{decorator}(depends_on={ref})\n"
        f"def {name}(ctx):\n"
        f"    relation = ctx.relation({ref})\n"
        f'    ctx.execute_sql(f"CREATE OR REPLACE TABLE main.{name}_result AS '
        f'SELECT count(*) AS n FROM {{relation}}")\n'
        f"    return {returned}\n\n\n"
    )


def python_node_selection_project_files(*, orders_sql: str) -> dict[str, str]:
    """Return a DuckDB project whose tasks and assets count managed, unmanaged, and model rows."""

    task_nodes: str = "".join(
        _counting_python_node(decorator="task", name=name, ref=ref, returned="None")
        for name, ref in (
            ("count_customers", 'source("raw_customers")'),
            ("count_raw_orders", 'source("raw_orders")'),
            ("count_orders", 'model("orders")'),
            ("count_order_summary", 'model("order_summary")'),
        )
    )
    asset_nodes: str = "".join(
        _counting_python_node(
            decorator="asset", name=name, ref=ref, returned="ctx.result(materialized=True)"
        )
        for name, ref in (
            ("customers_extract", 'source("raw_customers")'),
            ("orders_extract", 'model("orders")'),
        )
    )
    return {
        "sqlbuild_project.toml": (
            'name = "order_nodes"\nadapter = "duckdb"\n\n'
            f'[connection]\ndatabase = "{PYTHON_NODE_SELECTION_DATABASE}"\n'
        ),
        "sources/raw.yml": (
            "sources:\n"
            "  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            "  - name: raw_customers\n    managed: true\n    write_strategy: table\n"
            "    columns:\n      - name: customer_id\n        type: INTEGER\n"
        ),
        "python/loaders/customers.py": (
            "from sqlbuild.loaders import loader\n\n\n"
            "@loader\ndef raw_customers(ctx):\n    return [{'customer_id': 99}]\n"
        ),
        "python/tasks/counts.py": (
            "from sqlbuild.refs import model, source\nfrom sqlbuild.tasks import task\n\n\n"
            + task_nodes
        ),
        "python/assets/extracts.py": (
            "from sqlbuild.assets import asset\nfrom sqlbuild.refs import model, source\n\n\n"
            + asset_nodes
        ),
        "models/orders.sql": orders_sql,
        "models/order_summary.sql": (
            'MODEL (materialized table);\nSELECT count(*) AS order_count FROM __ref("orders")\n'
        ),
    }
