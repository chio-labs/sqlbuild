"""Real CLI coverage for targets that rely on the only named connection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    DefaultConnectionCliTestCase,
    InferredFreshnessCliTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    execute_duckdb_sql,
    query_duckdb_rows,
    write_default_connection_project,
)

_ONE_CONNECTION_PROJECT: str = (
    'name = "shop"\n'
    'adapter = "duckdb"\n'
    'default_target = "dev"\n\n'
    "[connections.local]\n"
    'database = "shop.duckdb"\n\n'
    "[targets.dev]\n"
    'schema = "dev"\n'
)
_SEVERAL_CONNECTIONS_PROJECT: str = (
    'name = "shop"\n'
    'adapter = "duckdb"\n'
    'default_target = "dev"\n\n'
    "[connections.local]\n"
    'database = "shop.duckdb"\n\n'
    "[connections.archive]\n"
    'database = "archive.duckdb"\n\n'
    "[targets.dev]\n"
    'schema = "dev"\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        DefaultConnectionCliTestCase(
            description="build writes into the only named connection",
            project_toml=_ONE_CONNECTION_PROJECT,
            argv=("build",),
            expected_exit_code=0,
            expected_output_fragments=("Completed successfully",),
            expected_order_rows=((1,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_without_connection_when_building_then_only_named_connection_is_used(
    test_case: DefaultConnectionCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_default_connection_project(project_dir=tmp_path, project_toml=test_case.project_toml)

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), *test_case.argv])

    output: str = "".join(capsys.readouterr())
    assert exit_code == test_case.expected_exit_code, output
    assert all(fragment in output for fragment in test_case.expected_output_fragments), output
    assert (
        query_duckdb_rows(db_path=tmp_path / "shop.duckdb", sql="SELECT order_id FROM dev.orders")
        == test_case.expected_order_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DefaultConnectionCliTestCase(
            description="debug reports the only named connection",
            project_toml=_ONE_CONNECTION_PROJECT,
            argv=("debug", "--no-connection"),
            expected_exit_code=0,
            expected_output_fragments=("connection: local", "shop.duckdb"),
        ),
        DefaultConnectionCliTestCase(
            description="build fails at config load among several named connections",
            project_toml=_SEVERAL_CONNECTIONS_PROJECT,
            argv=("build",),
            expected_exit_code=1,
            expected_output_fragments=(
                "error[D001]",
                "targets.dev does not set connection and several named connections are "
                "defined (archive, local)",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_without_connection_when_resolving_offline_then_connection_is_reported(
    test_case: DefaultConnectionCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_default_connection_project(project_dir=tmp_path, project_toml=test_case.project_toml)

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), *test_case.argv])

    output: str = "".join(capsys.readouterr())
    assert exit_code == test_case.expected_exit_code, output
    assert all(fragment in output for fragment in test_case.expected_output_fragments), output
    assert not (tmp_path / "shop.duckdb").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        InferredFreshnessCliTestCase(
            description="column key and declared timestamp column imply column timestamp",
            sources_yaml=(
                "sources:\n"
                "  - name: raw_orders\n"
                "    description: Raw orders.\n"
                "    schema: raw\n"
                "    table: orders\n"
                "    columns:\n"
                "      - name: updated_at\n"
                "        type: timestamp\n"
                "    freshness:\n"
                "      column: updated_at\n"
            ),
            expected_sources=(("raw_orders", "column", "timestamp", "2026-01-02T03:04:05+00:00"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_freshness_without_strategy_or_type_when_observing_then_both_are_inferred(
    test_case: InferredFreshnessCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_default_connection_project(project_dir=tmp_path, project_toml=_ONE_CONNECTION_PROJECT)
    (tmp_path / "sources").mkdir()
    _ = (tmp_path / "sources" / "raw.yml").write_text(test_case.sources_yaml, encoding="utf-8")
    execute_duckdb_sql(
        db_path=tmp_path / "shop.duckdb",
        sql=(
            "CREATE SCHEMA raw; "
            "CREATE TABLE raw.orders AS SELECT TIMESTAMP '2026-01-02 03:04:05' AS updated_at"
        ),
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "freshness", "--json"])

    captured: str = capsys.readouterr().out
    assert exit_code == 0, captured
    sources: list[dict[str, object]] = json.loads(captured)["sources"]
    assert (
        tuple(
            (
                source["name"],
                source["strategy"],
                source["value_kind"],
                source["current_data_version"],
            )
            for source in sources
        )
        == test_case.expected_sources
    )
