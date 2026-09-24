"""Helpers for janitor e2e tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from textwrap import dedent
from types import MappingProxyType

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_records
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessRecord,
    SourceFreshnessRenderers,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
)


def prepare_janitor_project(
    *,
    tmp_path: Path,
    project_name: str,
    janitor_config: str = "",
    settings_config: str = "",
) -> Path:
    """Create a minimal DuckDB project for janitor e2e tests."""

    normalized_settings_config: str = dedent(settings_config).strip()
    normalized_janitor_config: str = dedent(janitor_config).strip()
    settings_block: str = {False: "", True: f"\n[settings]\n{normalized_settings_config}\n"}[
        bool(normalized_settings_config)
    ]
    janitor_block: str = {False: "", True: f"\n[janitor]\n{normalized_janitor_config}\n"}[
        bool(normalized_janitor_config)
    ]
    project_config: str = (
        f'name = "{project_name}"\n'
        'adapter = "duckdb"\n\n'
        "[connection]\n"
        'database = "janitor.duckdb"\n'
        f"{settings_block}"
        f"{janitor_block}"
        "\n[defaults]\n"
        'materialized = "table"\n'
    )
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": project_config,
            "models/orders.sql": dedent(
                """
                MODEL ();

                SELECT 1 AS order_id
                """
            ).strip()
            + "\n",
        },
    )


def create_janitor_demo_relations(*, db_path: Path) -> None:
    """Create tracked, untracked, and excluded stale relations."""

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE janitor_tracked_extra AS SELECT 1 AS id")
        connection.execute("CREATE TABLE janitor_untracked_extra AS SELECT 1 AS id")
        connection.execute("CREATE TABLE partition_state AS SELECT 1 AS id")
        connection.execute("CREATE TABLE _sqlbuild_microbatches AS SELECT 1 AS id")
        write_fingerprint(
            connection=connection,
            execute=lambda *, connection, sql: connection.execute(sql),
            database=None,
            schema="main",
            fingerprint=Fingerprint(
                node_type="model",
                node_name="janitor_tracked_extra",
                target_database=None,
                target_schema="main",
                target_name="janitor_tracked_extra",
                run_id="run_janitor_e2e",
                definition_hash="definition_hash",
                schema_fingerprint="schema_hash",
                definition="SELECT 1 AS id",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
            render_qualified_name=DuckDbAdapter().render_qualified_name,
            render_framework_type=DuckDbAdapter().render_framework_type,
        )
        write_fingerprint(
            connection=connection,
            execute=lambda *, connection, sql: connection.execute(sql),
            database=None,
            schema="main",
            fingerprint=Fingerprint(
                node_type="model",
                node_name="microbatch_state_probe",
                target_database=None,
                target_schema="main",
                target_name="_sqlbuild_microbatches",
                run_id="run_janitor_microbatch_e2e",
                definition_hash="microbatch_definition_hash",
                schema_fingerprint="microbatch_schema_hash",
                definition="SELECT 1 AS id",
                ts=datetime(2026, 1, 15, 12, 0, 0),
            ),
            render_qualified_name=DuckDbAdapter().render_qualified_name,
            render_framework_type=DuckDbAdapter().render_framework_type,
        )
    finally:
        connection.close()


def create_janitor_scenario_relations(*, db_path: Path) -> None:
    """Create strict scenario artifacts and a similarly named non-artifact relation."""

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    try:
        connection.execute("CREATE TABLE __sqb_a13f09c2e7b8__source__raw_orders AS SELECT 1 AS id")
        connection.execute(
            "CREATE TABLE __sqb_a13f09c2e7b8__model__daily_revenue AS SELECT 1 AS id"
        )
        connection.execute("CREATE TABLE __sqb_a13f09c2e7b__model__daily_revenue AS SELECT 1 AS id")
    finally:
        connection.close()


def create_direct_state_history(*, db_path: Path) -> None:
    import duckdb

    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    try:
        run_id: str
        observed_hour: int
        for run_id, observed_hour in (
            ("run_000", 10),
            ("run_001", 12),
            ("run_002", 12),
            ("run_003", 13),
        ):
            write_fingerprint(
                connection=connection,
                execute=lambda *, connection, sql: connection.execute(sql),
                database=None,
                schema="main",
                fingerprint=Fingerprint(
                    node_type="model",
                    node_name="janitor_state_probe",
                    target_database=None,
                    target_schema="main",
                    target_name="janitor_state_probe",
                    run_id=run_id,
                    definition_hash=f"definition_{run_id}",
                    version_hash=f"version_{run_id}",
                    schema_fingerprint=f"schema_{run_id}",
                    definition=f"SELECT '{run_id}'",
                    ts=datetime(2026, 1, 15, observed_hour, 0, 0),
                ),
                render_qualified_name=adapter.render_qualified_name,
                render_framework_type=adapter.render_framework_type,
            )
            write_source_freshness_records(
                connection=connection,
                execute=lambda *, connection, sql: connection.execute(sql),
                database=None,
                schema="main",
                records=(
                    SourceFreshnessRecord(
                        source_name="raw.janitor_state_probe",
                        target_database=None,
                        target_schema=None,
                        target_name=None,
                        run_id=run_id,
                        strategy="adapter_metadata",
                        value_kind="timestamp",
                        data_version=f"2026-01-15T{observed_hour:02d}:00:00",
                        data_version_hash=f"source_{run_id}",
                        observed_at=datetime(2026, 1, 15, observed_hour, 5, 0, tzinfo=UTC),
                    ),
                ),
                renderers=SourceFreshnessRenderers(
                    render_qualified_name=adapter.render_qualified_name,
                    render_framework_type=adapter.render_framework_type,
                    render_insert_records_sql=adapter.render_insert_source_freshness_records_sql,
                ),
            )
    finally:
        connection.close()


AGED_JANITOR_ADAPTER_NAME: str = "aged_janitor_duckdb"
JANITOR_TEST_SETTINGS_FILENAME: str = "janitor_test_settings.json"
AGED_JANITOR_ADAPTER_SOURCE: str = """
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "janitor_test_settings.json"


def _settings() -> dict[str, Any]:
    if not _SETTINGS_PATH.exists():
        return {}
    return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))


class AgedJanitorDuckDbAdapter(DuckDbAdapter):
    adapter_name = "aged_janitor_duckdb"

    def supports_relation_age_metadata(self) -> bool:
        return True

    def maximum_identifier_length(self) -> int:
        return int(_settings().get("identifier_limit", super().maximum_identifier_length()))

    def list_relations(
        self,
        *,
        connection: Any,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        created_at: dict[str, str] = _settings().get("created_at", {})
        return tuple(
            replace(relation, created_at=datetime.fromisoformat(created_at[relation.name]))
            if relation.name in created_at
            else relation
            for relation in super().list_relations(
                connection=connection, database=database, schemas=schemas, names=names
            )
        )

    def _execute(self, *, connection: Any, sql: str) -> Any:
        if (
            _settings().get("fail_janitor_event_insert")
            and sql.startswith("INSERT INTO")
            and "_sqlbuild_janitor_events" in sql
        ):
            raise AdapterUserError("simulated janitor event write failure")
        return super()._execute(connection=connection, sql=sql)
"""


def prepare_archive_janitor_project(
    *,
    tmp_path: Path,
    project_name: str,
    janitor_config: str,
    model_names: tuple[str, ...] = ("orders",),
    use_aged_adapter: bool = False,
) -> Path:
    """Create a DuckDB project whose janitor archives stale relations."""

    repo_files: dict[str, str] = {
        "sqlbuild_project.toml": (
            f'name = "{project_name}"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            f'database = "{(tmp_path / project_name / "janitor.duckdb").as_posix()}"\n\n'
            f"[janitor]\n{dedent(janitor_config).strip()}\n\n"
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        **{
            f"models/{model_name}.sql": f"MODEL ();\n\nSELECT 1 AS {model_name}_id\n"
            for model_name in model_names
        },
        f"adapters/{AGED_JANITOR_ADAPTER_NAME}.py": AGED_JANITOR_ADAPTER_SOURCE,
        **{
            False: {},
            True: {"sqlbuild_local.toml": f'adapter = "{AGED_JANITOR_ADAPTER_NAME}"\n'},
        }[use_aged_adapter],
    }
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files=repo_files,
    )


def write_janitor_test_settings(
    *,
    project_dir: Path,
    created_at: Mapping[str, datetime] = MappingProxyType({}),
    identifier_limit: int = 255,
    fail_janitor_event_insert: bool = False,
) -> None:
    """Write relation ages and fault switches consumed by the aged janitor adapter."""

    import json

    payload: dict[str, object] = {
        "created_at": {name: value.isoformat() for name, value in created_at.items()},
        "identifier_limit": identifier_limit,
        "fail_janitor_event_insert": fail_janitor_event_insert,
    }
    (project_dir / JANITOR_TEST_SETTINGS_FILENAME).write_text(json.dumps(payload), encoding="utf-8")


def archive_timestamp_text(value: datetime) -> str:
    """Render the UTC timestamp component embedded in janitor archive names."""

    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def list_archive_names(*, db_path: Path, schema: str = "main") -> tuple[str, ...]:
    """Return archive-prefixed relation names in one schema."""

    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' AND starts_with(table_name, '_SQB_ARCHIVE__') "
            "ORDER BY table_name"
        ),
    )
    return tuple(str(row[0]) for row in rows)


def read_janitor_events(*, db_path: Path) -> list[tuple[object, ...]]:
    """Return janitor audit rows in a stable order."""

    return query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT event_type, original_name, original_qualified_name, archive_name, run_id "
            "FROM main._sqlbuild_janitor_events ORDER BY occurred_at, event_type, archive_name"
        ),
    )


def read_current_janitor_events(*, db_path: Path, run_id: str) -> list[tuple[object, ...]]:
    """Return janitor audit rows excluding one seeded historical run."""

    return query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT event_type, original_name, original_qualified_name, archive_name, run_id "
            f"FROM main._sqlbuild_janitor_events WHERE run_id <> '{run_id}' "
            "ORDER BY archive_name"
        ),
    )
