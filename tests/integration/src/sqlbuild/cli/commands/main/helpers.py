from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import duckdb
import pytest

from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import RetentionChangePhase
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.commands._helpers.compile import target_writer
from sqlbuild.cli.commands.classes import prepared_compile_artifacts
from sqlbuild.cli.commands.classes.prepared_compile_artifacts import PreparedCompileArtifacts
from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.cli.compile.models import PlannedStaticSqlTests
from sqlbuild.compiler.compile._helpers.assembly import source_bindings as source_bindings_module
from sqlbuild.compiler.compile.models import PolyglotAnalysisResult
from sqlbuild.compiler.discovery._helpers.filesystem import (
    model_files as discovery_model_files_module,
)
from sqlbuild.compiler.planner.exceptions import NativeSqlTestPlanningError
from sqlbuild.compiler.planner.models import NativeSqlTestArtifact
from sqlbuild.spec.contracts.models import SourceLocation
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    RepeatedJsonParseTestCase,
)


def staging_directories(target_dir: Path) -> list[str]:
    """Return hidden entries left in target_dir, such as abandoned artifact staging."""

    return sorted(path.name for path in target_dir.glob(".*"))


def write_staging_directory(*, target_dir: Path, name: str) -> Path:
    """Write one artifact staging directory with a staged model file."""

    directory: Path = target_dir / name
    (directory / "compiled" / "models").mkdir(parents=True)
    (directory / "compiled" / "models" / "orders.sql").write_text("SELECT 1\n", encoding="utf-8")
    return directory


def write_prepared_artifacts_project(*, project_dir: Path, model_count: int) -> None:
    """Write a DuckDB project large enough to stage compile artifacts in the background."""

    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = ["SQBRSQL021"]\n',
        encoding="utf-8",
    )
    models: Path = project_dir / "models"
    models.mkdir()
    for index in range(model_count):
        (models / f"orders_{index:03}.sql").write_text(
            "MODEL (description 'Test model.', materialized table, contract enforced, "
            "columns (order_id (type INTEGER)));\n"
            f"SELECT CAST({index} AS INTEGER) AS order_id\n",
            encoding="utf-8",
        )


SELECTED_RULES_CONFIG: str = '[rules]\nselect = ["SQBRSQL021"]\n'
TEST_PLANNING_MODELS: int = 6


def write_test_planning_project(
    *, project_dir: Path, model_count: int, rules_config: str, test_options: str = ""
) -> None:
    """Write a chain of DuckDB models with one SQL test per downstream model."""

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "duckdb"\n{rules_config}', encoding="utf-8"
    )
    models: Path = project_dir / "models"
    tests: Path = project_dir / "tests" / "unit"
    models.mkdir()
    tests.mkdir(parents=True)
    header: str = (
        "MODEL (description 'Test model.', materialized table, contract enforced, "
        "columns (order_id (type INTEGER)));\n"
    )
    (models / "orders_000.sql").write_text(
        header + "SELECT CAST(0 AS INTEGER) AS order_id\n", encoding="utf-8"
    )
    for index in range(1, model_count):
        upstream: str = f"orders_{index - 1:03}"
        (models / f"orders_{index:03}.sql").write_text(
            header + f'SELECT CAST(order_id + 1 AS INTEGER) AS order_id FROM __ref("{upstream}")\n',
            encoding="utf-8",
        )
        write_order_test(
            tests_dir=tests, index=index, expected_order_id=2, test_options=test_options
        )


def write_order_test(
    *, tests_dir: Path, index: int, expected_order_id: int, test_options: str = ""
) -> None:
    """Write the SQL test for one chained order model with a mocked upstream model."""

    (tests_dir / f"orders_{index:03}.sql").write_text(
        f'TEST (name "orders_{index:03}_case"{test_options});\n'
        "WITH\n"
        f"__ref__orders_{index - 1:03} AS (SELECT CAST(1 AS INTEGER) AS order_id),\n"
        f"__expected__orders_{index:03} AS "
        f"(SELECT CAST({expected_order_id} AS INTEGER) AS order_id)\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def compiled_files(project_dir: Path) -> dict[str, bytes]:
    """Return every compiled artifact under target/compiled keyed by relative path."""

    compiled: Path = project_dir / "target" / "compiled"
    return {
        str(path.relative_to(compiled)): path.read_bytes()
        for path in sorted(compiled.rglob("*.sql"))
    }


def semantic_compile_payload(output: str) -> dict[str, object]:
    """Return compile JSON without its timings and version, which vary between runs."""

    payload: dict[str, object] = json.loads(output)
    payload.pop("compile_timings", None)
    payload.pop("version", None)
    return payload


def compile_project_json(
    *, project_dir: Path, compile_args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> tuple[int, dict[str, object]]:
    """Compile through the CLI and return the exit code with the semantic JSON payload."""

    exit_code: int = main(["--project-dir", str(project_dir), "compile", "--json", *compile_args])
    return exit_code, semantic_compile_payload(capsys.readouterr().out)


def keep_project_unchanged(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Leave a freshly written project cold, with no target directory."""


def compile_then_edit_one_test(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Warm the compile cache, then change one SQL test so only it must be planned again."""

    assert compile_project_json(project_dir=project_dir, compile_args=(), capsys=capsys)[0] == 0
    write_order_test(tests_dir=project_dir / "tests" / "unit", index=2, expected_order_id=3)


def keep_native_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave the real native SQL-test planner in place."""


def fail_native_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the native SQL-test planner fail as an unexpected internal error would."""

    def fail(**kwargs: object) -> tuple[NativeSqlTestArtifact, ...]:
        raise NativeSqlTestPlanningError("native SQL-test planning failed: worker stopped")

    monkeypatch.setattr(target_writer, "plan_and_render_sql_test_artifacts", fail)


def record_test_planning_threads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the thread-name prefix of every background SQL-test planning task."""

    threads: list[str] = []
    plan: Callable[..., PlannedStaticSqlTests] = prepared_compile_artifacts.plan_static_sql_tests

    def recorded_plan(**kwargs: Any) -> PlannedStaticSqlTests:
        threads.append(threading.current_thread().name.rpartition("_")[0])
        return plan(**kwargs)

    monkeypatch.setattr(prepared_compile_artifacts, "plan_static_sql_tests", recorded_plan)
    return threads


def skip_artifact_preparation(self: PreparedCompileArtifacts, **kwargs: object) -> None:
    """Disable background preparation so the write phase plans SQL tests inline."""


def has_second_filesystem(root: Path) -> bool:
    """Return whether root is a writable directory on another device than the temp directory."""

    return (
        root.is_dir()
        and os.access(root, os.W_OK)
        and root.stat().st_dev != Path(tempfile.gettempdir()).stat().st_dev
    )


def unavailable_staging_directory(staging_dir: Path) -> None:
    raise OSError(f"staging storage unavailable for {staging_dir.name}")


def write_compile_startup_project(project_dir: Path) -> None:
    """Write the minimal project used by fresh-process import tests."""

    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    models_dir: Path = project_dir / "models"
    models_dir.mkdir()
    (models_dir / "orders.sql").write_text(
        "MODEL (description 'Test model orders.', materialized table);\nSELECT 1 AS order_id\n",
        encoding="utf-8",
    )


def write_from_values_format_project(*, tmp_path: Path, adapter: str) -> tuple[Path, Path]:
    """Write a format project containing an authored values relation."""

    project_dir: Path = tmp_path / adapter
    project_dir.mkdir()
    (project_dir / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "{adapter}"\n\n[rules]\nselect = ["SQBRSQL039"]\n',
        encoding="utf-8",
    )
    models: Path = project_dir / "models"
    models.mkdir()
    (models / "customers.sql").write_text(
        'MODEL (description "Customers.");\nSELECT 1 AS customer_key, 1 AS order_count\n',
        encoding="utf-8",
    )
    (models / "orders.sql").write_text(
        'MODEL (description "Orders.");\nSELECT customer_key, 1 AS order_count '
        'FROM __ref("customers")\n',
        encoding="utf-8",
    )
    test_file: Path = project_dir / "tests" / "unit" / "test_orders.sql"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        'TEST (name "orders_from_values");\n\n'
        "WITH __ref__customers AS (\n"
        "    SELECT COLUMN1::VARCHAR AS customer_key, COLUMN2::INTEGER AS order_count\n"
        "    FROM VALUES\n"
        "        ('c1', 1),\n"
        "        ('c2', 2)\n"
        "),\n"
        "__expected__orders AS (SELECT 'c1' AS customer_key, 1 AS order_count)\n"
        "SELECT 1\n",
        encoding="utf-8",
    )
    return project_dir, test_file


def write_snowflake_format_test(*, tmp_path: Path, test_sql: str) -> tuple[Path, Path]:
    """Write a minimal Snowflake-dialect project for real CLI formatting."""

    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "products"\nadapter = "snowflake"\n', encoding="utf-8"
    )
    test_file: Path = tmp_path / "tests" / "unit" / "test_products.sql"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(test_sql, encoding="utf-8")
    return tmp_path, test_file


def prepare_contract_project(tmp_path: Path, *, prod_connection_toml: str = "") -> Path:
    database: Path = tmp_path / "warehouse.duckdb"
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        (
            'name = "contract_test"\n'
            'adapter = "duckdb"\n'
            'default_target = "dev"\n'
            f'\n[connection]\ndatabase = "{database}"\n'
            '\n[targets.dev]\nschema = "dev"\n'
            '\n[targets.prod]\nschema = "prod"\n'
            f"{prod_connection_toml}"
        ),
        encoding="utf-8",
    )
    models: Path = tmp_path / "models"
    sources: Path = tmp_path / "sources"
    models.mkdir()
    sources.mkdir()
    _ = (models / "orders.sql").write_text(
        """MODEL (description "Test model orders.",
  materialized table
  -- keep model metadata
  columns (
    id ()
  )
);
SELECT CAST(1 AS INTEGER) AS id, CAST('a' AS VARCHAR) AS name
""",
        encoding="utf-8",
    )
    _ = (sources / "raw.yml").write_text(
        """sources:
  - name: raw_orders
    schema: raw
    table: orders
    description: keep source
    columns:
      - name: id
        description: identifier
""",
        encoding="utf-8",
    )
    with duckdb.connect(str(database)) as connection:
        connection.execute("CREATE SCHEMA prod")
        connection.execute("CREATE SCHEMA raw")
        connection.execute("CREATE TABLE prod.orders(id INTEGER, name VARCHAR)")
        connection.execute("CREATE TABLE raw.orders(id BIGINT, status VARCHAR)")
    return database


def add_second_contract_source(*, project_dir: Path, database: Path) -> None:
    """Add another physical source declared in the existing source YAML file."""

    source_path: Path = project_dir / "sources" / "raw.yml"
    _ = source_path.write_text(
        source_path.read_text(encoding="utf-8")
        + """  - name: raw_customers
    schema: raw
    table: customers
    description: keep second source
""",
        encoding="utf-8",
    )
    with duckdb.connect(str(database)) as connection:
        connection.execute("ALTER TABLE raw.orders ADD COLUMN generated_at TIMESTAMP")
        connection.execute("CREATE TABLE raw.customers(customer_id BIGINT, email VARCHAR)")


def compile_finding_keys(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> set[str]:
    """Compile through the CLI and return diagnostics as path:code keys."""

    _ = main(["--project-dir", str(project_dir), "compile", "--json"])
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, object]] = cast(list[dict[str, object]], payload["diagnostics"])
    return {f"{item['path']}:{item['code']}" for item in diagnostics}


class LiveRetentionFake:
    """Pretend every managed table currently keeps a fixed number of retention days."""

    def __init__(self, *, live_days: int) -> None:
        self.live_days: int = live_days
        self.requested_days: list[int] = []

    def inspect_retention(self, *, connection: object, request: RetentionRequest) -> RetentionState:
        del connection
        return RetentionState(
            request_id=request.request_id,
            scope=request.scope,
            configured_days=self.live_days,
            effective_days=self.live_days,
        )

    def render_retention_changes(
        self, *, request: RetentionRequest, state: RetentionState | None = None
    ) -> tuple[RenderedRetentionChange, ...]:
        del state
        self.requested_days.append(request.desired_days)
        return (
            RenderedRetentionChange(phase=RetentionChangePhase.ALTER, statements=("SELECT 1",)),
        )


def install_live_retention_fake(
    *, monkeypatch: pytest.MonkeyPatch, fake: LiveRetentionFake
) -> None:
    """Route DuckDB retention inspection and rendering through the fake."""

    monkeypatch.setattr(
        DuckDbAdapter,
        "inspect_retention",
        lambda _self, *, connection, request: fake.inspect_retention(
            connection=connection, request=request
        ),
    )
    monkeypatch.setattr(
        DuckDbAdapter,
        "render_retention_changes",
        lambda _self, *, request, state=None: fake.render_retention_changes(
            request=request, state=state
        ),
    )


def write_retention_policy_project(*, project_dir: Path, target_lines: tuple[str, ...]) -> None:
    """Write a DuckDB project with one table and one view under a prod target."""

    (project_dir / "models").mkdir(parents=True, exist_ok=True)
    _ = (project_dir / "sqlbuild_project.toml").write_text(
        "\n".join(
            (
                'name = "demo"',
                'adapter = "duckdb"',
                'default_target = "prod"',
                "",
                "[connection]",
                'database = "demo.duckdb"',
                "",
                "[materialization_defaults.table]",
                'time_travel_retention = "90d"',
                "",
                "[targets.prod]",
                *target_lines,
                "",
            )
        ),
        encoding="utf-8",
    )
    _ = (project_dir / "models" / "orders.sql").write_text(
        "MODEL (description 'Test model orders.', materialized table);\n\nSELECT 1 AS order_id\n",
        encoding="utf-8",
    )
    _ = (project_dir / "models" / "order_view.sql").write_text(
        'MODEL (description "Test model order_view.", '
        'materialized view);\n\nSELECT order_id FROM __ref("orders")\n',
        encoding="utf-8",
    )


def run_build(
    *, project_dir: Path, flags: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    """Run one real CLI build and return its exit code and combined output."""

    exit_code: int = main(["--project-dir", str(project_dir), "--no-color", "build", *flags])
    return exit_code, "".join(capsys.readouterr())


def built_model_rows(
    *, project_dir: Path, model: str, capsys: pytest.CaptureFixture[str]
) -> list[tuple[Any, ...]]:
    """Build the project into its `orders.duckdb` and return one model's rows in a stable order."""

    exit_code, output = run_build(project_dir=project_dir, flags=(), capsys=capsys)
    assert exit_code == 0, output
    with duckdb.connect(str(project_dir / "orders.duckdb"), read_only=True) as connection:
        return sorted(connection.execute(f"SELECT * FROM {model}").fetchall(), key=repr)


def rule_fix_statuses(*, payload: dict[str, Any], code: str, file_name: str) -> tuple[str, ...]:
    """Statuses of one Rule's fixes in one file, from `format --fix --json` output."""

    key: tuple[str, str] = (code, file_name)
    statuses: dict[tuple[str, str], list[str]] = {key: []}
    for fix in payload["rule_fixes"]:
        statuses.setdefault((fix["code"], Path(fix["file"]).name), []).append(fix["status"])
    return tuple(statuses[key])


def write_dropped_relation_project(
    *, project_dir: Path, model_name: str, model_sql: str, settings_toml: str = ""
) -> Path:
    """Write a DuckDB project with raw order sources, one seed, and one model."""

    (project_dir / "models").mkdir(parents=True, exist_ok=True)
    (project_dir / "sources").mkdir(parents=True, exist_ok=True)
    (project_dir / "seeds").mkdir(parents=True, exist_ok=True)
    _ = (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[connection]\ndatabase = "orders.duckdb"\n'
        + settings_toml,
        encoding="utf-8",
    )
    _ = (project_dir / "sources" / "raw.yml").write_text(
        "sources:\n"
        "  - name: raw_orders\n    description: Test source raw_orders.\n"
        "    schema: main\n"
        "    table: raw_orders\n"
        "  - name: raw_customers\n    description: Test source raw_customers.\n"
        "    schema: main\n"
        "    table: raw_customers\n",
        encoding="utf-8",
    )
    _ = (project_dir / "seeds" / "order_statuses.csv").write_text(
        "status_code,status_name\n1,placed\n2,shipped\n", encoding="utf-8"
    )
    _ = (project_dir / "seeds" / "lookups.yml").write_text(
        "seeds:\n"
        "  - name: order_statuses\n    description: Test seed order_statuses.\n"
        "    columns:\n"
        "      - name: status_code\n"
        "        type: INTEGER\n"
        "      - name: status_name\n"
        "        type: VARCHAR\n",
        encoding="utf-8",
    )
    _ = (project_dir / "models" / f"{model_name}.sql").write_text(model_sql, encoding="utf-8")
    db_path: Path = project_dir / "orders.duckdb"
    execute_duckdb_sql(
        db_path=db_path,
        sql=(
            "CREATE TABLE main.raw_orders (id INTEGER, ordered_at TIMESTAMP); "
            "INSERT INTO main.raw_orders VALUES "
            "(1, '2026-01-01 05:00:00'), (2, '2026-01-02 01:00:00'), "
            "(3, '2026-01-03 01:00:00'); "
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2026-01-01' AS updated_at"
        ),
    )
    return db_path


def execute_duckdb_sql(*, db_path: Path, sql: str) -> None:
    """Run mutating SQL directly against a DuckDB file, outside SQLBuild."""

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    try:
        _ = connection.execute(sql)
    finally:
        connection.close()


def query_duckdb_rows(*, db_path: Path, sql: str) -> tuple[tuple[object, ...], ...]:
    """Read rows directly from a DuckDB file."""

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path), read_only=True)
    try:
        return tuple(tuple(row) for row in connection.execute(sql).fetchall())
    finally:
        connection.close()


def run_plan_json(
    *, project_dir: Path, flags: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> dict[str, object]:
    """Run one real CLI JSON plan and return the parsed document."""

    _ = capsys.readouterr()
    exit_code: int = main(["--project-dir", str(project_dir), "plan", "--json", *flags])
    out: str
    err: str
    out, err = capsys.readouterr()
    assert exit_code == 0, out + err
    return cast(dict[str, object], json.loads(out))


def plan_model(*, plan: dict[str, object], name: str) -> dict[str, object]:
    """Return one serialized model entry from a JSON plan."""

    models: list[dict[str, object]] = cast(list[dict[str, object]], plan["models"])
    return {str(model["name"]): model for model in models}[name]


def plan_warning_identities(*, plan: dict[str, object]) -> tuple[tuple[object, object], ...]:
    """Return the resource name and diagnostic code of every plan warning."""

    warnings: list[dict[str, object]] = cast(list[dict[str, object]], plan["warnings"])
    return tuple((warning.get("model_name"), warning.get("code")) for warning in warnings)


def plan_cursor_bounds(*, plan: dict[str, object], name: str) -> dict[str, object]:
    """Return the serialized cursor bounds of one planned model."""

    return cast(dict[str, object], plan_model(plan=plan, name=name)["cursor_bounds"])


def plan_seed_reasons(*, plan: dict[str, object]) -> dict[str, object]:
    """Return plan reasons keyed by seed name."""

    seeds: list[dict[str, object]] = cast(list[dict[str, object]], plan["seeds"])
    return {str(seed["name"]): seed["reason"] for seed in seeds}


def dropped_relation_microbatch_sql(*, batch_concurrency: int) -> str:
    """Render an integer-cursor microbatch model over the raw order source."""

    return (
        "MODEL (description 'Test model.',\n"
        "  materialized incremental,\n"
        "  incremental_strategy delete_insert,\n"
        "  incremental_mode microbatch,\n"
        "  microbatch_strategy watermark,\n"
        "  cursor_watermark_mode all,\n"
        "  cursor id,\n"
        "  cursor_type integer,\n"
        "  cursor_inputs (raw_orders (column id, roles [filter, watermark]),),\n"
        '  batch_size "1",\n'
        f"  batch_concurrency {batch_concurrency},\n"
        ");\n\n"
        'SELECT id, ordered_at FROM __source("raw_orders")\n'
        "WHERE id >= __cursor_start() AND id < __cursor_end()\n"
    )


def compile_duckdb_projection(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str], projection: str
) -> tuple[int, tuple[object, ...]]:
    """Compile one DuckDB model projection and return the exit and diagnostic codes."""

    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "orders.sql").write_text(
        f"MODEL (description 'Test model orders.');\nSELECT {projection}"
    )
    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    result: dict[str, object] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, object]] = cast(list[dict[str, object]], result["diagnostics"])
    return exit_code, tuple(item["code"] for item in diagnostics)


def write_expression_source_project(
    *, project_dir: Path, source_expression: str, model_sql: str
) -> None:
    """Write a DuckDB project with one typed expression source and one reading model."""

    (project_dir / "sources").mkdir(parents=True)
    (project_dir / "models").mkdir()
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[connection]\ndatabase = "orders.duckdb"\n',
        encoding="utf-8",
    )
    (project_dir / "sources" / "orders.yml").write_text(
        "sources:\n"
        "  - name: typed_orders\n    description: Test source typed_orders.\n"
        f'    expression: "{source_expression}"\n'
        "    columns:\n"
        "      - name: order_id\n"
        "        type: INTEGER\n",
        encoding="utf-8",
    )
    (project_dir / "models" / "orders.sql").write_text(model_sql, encoding="utf-8")


def record_source_rebinding_analyses(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every model query analysed again against inspected source columns."""

    analysed: list[str] = []
    original: Callable[..., PolyglotAnalysisResult] = (
        source_bindings_module.analyze_columns_and_lineage_with_polyglot
    )

    def recording(**kwargs: Any) -> PolyglotAnalysisResult:
        analysed.append(str(kwargs["query_sql"]))
        return original(**kwargs)

    monkeypatch.setattr(
        source_bindings_module, "analyze_columns_and_lineage_with_polyglot", recording
    )
    return analysed


def record_eager_output_column_scans(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record every model file whose output columns discovery locates eagerly."""

    scanned: list[Path] = []
    original: Callable[..., dict[str, SourceLocation]] = (
        discovery_model_files_module.matched_model_output_column_locations
    )

    def recording(**kwargs: Any) -> dict[str, SourceLocation]:
        scanned.append(cast(Path, kwargs["relative_path"]))
        return original(**kwargs)

    monkeypatch.setattr(
        discovery_model_files_module, "matched_model_output_column_locations", recording
    )
    return scanned


def write_repeated_json_parse_project(
    *, tmp_path: Path, test_case: RepeatedJsonParseTestCase
) -> None:
    """Write a one-model project that selects only SQBRSQL045."""

    (tmp_path / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "{test_case.adapter}"\n\n[rules]\nselect = ["SQBRSQL045"]\n',
        encoding="utf-8",
    )
    files: tuple[tuple[str, str], ...] = (
        ("models/order_events.sql", f"{test_case.header}{test_case.sql}"),
        *test_case.extra_files,
    )
    for relative_path, contents in files:
        path: Path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
