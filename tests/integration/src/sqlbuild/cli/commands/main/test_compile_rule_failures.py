"""Real CLI coverage for the compiled SQL a compile writes when Rules fail."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import COMPILE_REUSE_DISABLE_ENV_VAR, DELTA_COMPILE_VERIFY_ENV_VAR
from sqlbuild._native import run_cli as main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    RuleFailureArtifactsTestCase,
    RuleFailureSequenceTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    artifact_tree,
    open_orders_model,
    write_project_files,
)

_PROJECT: str = (
    'name = "shop"\n'
    'adapter = "duckdb"\n'
    'default_target = "dev"\n\n'
    "[connections.local]\n"
    'database = "shop.duckdb"\n\n'
    "[targets.dev]\n"
    'connection = "local"\n'
    'schema = "dev"\n\n'
    "[rules]\n"
    'select = ["SQBRSQL028"]\n'
)
_ORDERS: str = (
    'MODEL (\n  description "One row per order",\n  materialized table,\n);\n\n'
    "SELECT 1 AS order_id, 'open' AS status\n"
)
_CUSTOMERS: str = (
    'MODEL (\n  description "One row per customer",\n  materialized table,\n);\n\n'
    "SELECT 1 AS customer_id\n"
)
_ORDERS_SQL: bytes = b"SELECT 1 AS order_id, 'open' AS status\n"
_PASSING: str = 'SELECT o.order_id, o.status FROM __ref("orders") AS o'
_FAILING: str = 'SELECT o.order_id, status FROM __ref("orders") AS o'
_FAILED_OPEN_ORDERS: bytes = (
    b"-- sqb: compile failed for this model; not buildable\n"
    b"-- SQBRSQL028 at models/open_orders.sql:6:20: "
    b"Single-relation query mixes qualified and unqualified columns\n"
    b'SELECT o.order_id, status FROM __ref("orders") AS o\n'
)
_PASSING_OPEN_ORDERS: bytes = b'SELECT o.order_id, o.status FROM __ref("orders") AS o\n'
_REUSED_LINE: str = "reused the previous compile"
_VERIFIED_LINE: str = "delta compile verified"


@pytest.mark.parametrize(
    "test_case",
    [
        RuleFailureArtifactsTestCase(
            description=(
                "a failing compile writes compiled-failed/ with a header on the failing model "
                "and leaves compiled/ as the last passing compile wrote it"
            ),
            open_orders_sql=_FAILING,
            expected_exit_code=1,
            expected_compiled={
                "models/open_orders.sql": _PASSING_OPEN_ORDERS,
                "models/orders.sql": _ORDERS_SQL,
                "models/retired_orders.sql": _ORDERS_SQL,
            },
            expected_failed={
                "models/open_orders.sql": _FAILED_OPEN_ORDERS,
                "models/orders.sql": _ORDERS_SQL,
            },
            expected_manifest=False,
            expected_output_fragment=(
                "Failed SQL: target/compiled-failed/models/open_orders.sql\n"
                "  Wrote: target/compiled-failed/\n"
            ),
        ),
        RuleFailureArtifactsTestCase(
            description="a passing compile replaces compiled/ and writes no compiled-failed/",
            open_orders_sql=_PASSING.replace("o.status", "o.status AS order_status"),
            expected_exit_code=0,
            expected_compiled={
                "models/open_orders.sql": _PASSING_OPEN_ORDERS.replace(
                    b"o.status", b"o.status AS order_status"
                ),
                "models/orders.sql": _ORDERS_SQL,
            },
            expected_failed={},
            expected_manifest=True,
            expected_output_fragment="Wrote: target/compiled/\n",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rule_findings_when_compiling_then_failed_sql_is_written_beside_compiled(
    test_case: RuleFailureArtifactsTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_project_files(
        project_dir=tmp_path,
        files={
            "sqlbuild_project.toml": _PROJECT,
            "models/orders.sql": _ORDERS,
            "models/open_orders.sql": open_orders_model(_PASSING),
            "models/retired_orders.sql": _ORDERS,
        },
    )
    compile_args: list[str] = [
        "--no-color",
        "--project-dir",
        str(tmp_path),
        "compile",
        "--manifest",
    ]
    assert main(compile_args) == 0
    _ = capsys.readouterr()
    assert (tmp_path / "target" / "manifest.json").exists()
    write_project_files(
        project_dir=tmp_path,
        files={"models/open_orders.sql": open_orders_model(test_case.open_orders_sql)},
    )
    (tmp_path / "models" / "retired_orders.sql").unlink()

    exit_code: int = main(compile_args)

    output: str = "".join(capsys.readouterr())
    failed: Path = tmp_path / "target" / "compiled-failed"
    assert exit_code == test_case.expected_exit_code, output
    assert test_case.expected_output_fragment in output
    assert artifact_tree(tmp_path / "target" / "compiled") == test_case.expected_compiled
    assert artifact_tree(failed) == test_case.expected_failed
    assert failed.exists() is bool(test_case.expected_failed)
    assert (tmp_path / "target" / "manifest.json").exists() is test_case.expected_manifest
    assert not (tmp_path / "target" / "compiled-models.txt").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        RuleFailureSequenceTestCase(
            description="with the compile cache",
            environment={COMPILE_REUSE_DISABLE_ENV_VAR: "0"},
            extra_args=(),
            expected_rewarm_reused=True,
            expected_minimum_verified_deltas=0,
        ),
        RuleFailureSequenceTestCase(
            description="with each delta compile checked against a full compile",
            environment={COMPILE_REUSE_DISABLE_ENV_VAR: "0", DELTA_COMPILE_VERIFY_ENV_VAR: "1"},
            extra_args=(),
            expected_rewarm_reused=True,
            expected_minimum_verified_deltas=5,
        ),
        RuleFailureSequenceTestCase(
            description="without the compile cache",
            environment={},
            extra_args=("--no-cache",),
            expected_rewarm_reused=False,
            expected_minimum_verified_deltas=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_and_passing_compiles_when_alternating_then_compiled_failed_follows_the_latest(
    test_case: RuleFailureSequenceTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in test_case.environment.items():
        monkeypatch.setenv(name, value)
    write_project_files(
        project_dir=tmp_path,
        files={
            "sqlbuild_project.toml": _PROJECT,
            "models/customers.sql": _CUSTOMERS,
            "models/orders.sql": _ORDERS,
            "models/open_orders.sql": open_orders_model(_PASSING),
        },
    )
    compiled: Path = tmp_path / "target" / "compiled"
    failed: Path = tmp_path / "target" / "compiled-failed"
    compile_args: list[str] = [
        "--no-color",
        "--project-dir",
        str(tmp_path),
        "compile",
        *test_case.extra_args,
    ]
    stderr_lines: list[str] = []

    def compiled_once(expected_exit_code: int) -> str:
        exit_code: int = main(compile_args)
        stdout, stderr = capsys.readouterr()
        assert exit_code == expected_exit_code, stdout + stderr
        stderr_lines.extend(stderr.splitlines())
        return stderr

    def rewarmed(expected_exit_code: int) -> None:
        stderr: str = compiled_once(expected_exit_code)
        assert (_REUSED_LINE in stderr) is test_case.expected_rewarm_reused, stderr

    def edited(files: dict[str, str]) -> None:
        write_project_files(project_dir=tmp_path, files=files)

    compiled_once(0)
    first_pass: dict[str, bytes] = artifact_tree(compiled)
    failing: dict[str, bytes] = {
        "models/customers.sql": b"SELECT 1 AS customer_id\n",
        "models/open_orders.sql": _FAILED_OPEN_ORDERS,
        "models/orders.sql": _ORDERS_SQL,
    }
    assert sorted(first_pass) == [
        "models/customers.sql",
        "models/open_orders.sql",
        "models/orders.sql",
    ]
    assert not failed.exists()

    edited(
        {"models/open_orders.sql": open_orders_model(_FAILING), "models/new_orders.sql": _ORDERS}
    )
    compiled_once(1)
    assert artifact_tree(compiled) == first_pass
    assert artifact_tree(failed) == {**failing, "models/new_orders.sql": _ORDERS_SQL}

    (tmp_path / "models" / "new_orders.sql").unlink()
    compiled_once(1)
    rewarmed(1)
    assert artifact_tree(compiled) == first_pass
    assert artifact_tree(failed) == failing

    edited({"models/open_orders.sql": open_orders_model(_PASSING)})
    compiled_once(0)
    assert not failed.exists()
    assert artifact_tree(compiled) == first_pass

    edited({"models/open_orders.sql": open_orders_model(_FAILING)})
    compiled_once(1)
    assert artifact_tree(failed) == failing
    assert artifact_tree(compiled) == first_pass

    edited({"models/customers.sql": _CUSTOMERS.replace("1 AS", "2 AS")})
    compiled_once(1)
    rewarmed(1)
    assert artifact_tree(failed) == {
        **failing,
        "models/customers.sql": b"SELECT 2 AS customer_id\n",
    }
    assert artifact_tree(compiled) == first_pass

    edited({"models/open_orders.sql": open_orders_model(_PASSING)})
    compiled_once(0)
    rewarmed(0)
    assert not failed.exists()
    assert artifact_tree(compiled) == {
        **first_pass,
        "models/customers.sql": b"SELECT 2 AS customer_id\n",
    }

    edited({"models/customers.sql": _CUSTOMERS})
    compiled_once(0)
    rewarmed(0)
    assert not failed.exists()
    assert artifact_tree(compiled) == first_pass
    assert stderr_lines.count(_VERIFIED_LINE) >= test_case.expected_minimum_verified_deltas
