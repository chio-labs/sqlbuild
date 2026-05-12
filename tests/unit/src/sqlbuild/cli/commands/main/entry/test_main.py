from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entry import _main_with_dependencies, main
from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from tests.unit.src.sqlbuild.cli.commands.main.entry._test_types import (
    MainErrorRenderingTestCase,
    MainTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.entry.helpers import build_handlers

ERROR_RENDERING_TEST_CASES: list[MainErrorRenderingTestCase] = [
    MainErrorRenderingTestCase(
        description="renders discovery errors without a traceback",
        argv=["--project-dir", "/tmp/demo", "compile"],
        error_type=ProjectConfigError,
        error_factory=lambda project_dir: ProjectConfigError(
            f"{project_dir / 'sqlbuild_project.toml'} must define non-empty string 'name'"
        ),
        expected_stderr_fragment=(
            "error[D001]: /tmp/demo/sqlbuild_project.toml must define non-empty string 'name'"
        ),
        expected_exit_code=1,
    ),
    MainErrorRenderingTestCase(
        description="renders cli user errors without a traceback",
        argv=["--project-dir", "/tmp/demo", "compile"],
        error_type=CliUserError,
        error_factory=lambda project_dir: CliUserError("bad command usage", code="C999"),
        expected_stderr_fragment="error[C999]: bad command usage",
        expected_exit_code=1,
    ),
    MainErrorRenderingTestCase(
        description="renders compile input errors with a code",
        argv=["--project-dir", "/tmp/demo", "compile"],
        error_type=CompileInputError,
        error_factory=lambda project_dir: CompileInputError("model config is invalid"),
        expected_stderr_fragment="error[P001]: model config is invalid",
        expected_exit_code=1,
    ),
    MainErrorRenderingTestCase(
        description="renders plain value errors without a traceback",
        argv=["--project-dir", "/tmp/demo", "compile"],
        error_type=ValueError,
        error_factory=lambda project_dir: ValueError("invalid compile request"),
        expected_stderr_fragment="error[E001]: invalid compile request",
        expected_exit_code=1,
    ),
    MainErrorRenderingTestCase(
        description="renders query user errors without a traceback",
        argv=["query", "SELECT 1"],
        error_type=CliUserError,
        error_factory=lambda project_dir: CliUserError(
            "query requires SQL",
            code="C102",
            help="pass SQL as the query argument",
        ),
        expected_stderr_fragment=(
            "error[C102]: query requires SQL\n  = help: pass SQL as the query argument"
        ),
        expected_exit_code=1,
    ),
]

COMMAND_LOCAL_GLOBAL_FLAG_ERROR_TEST_CASES: list[MainTestCase] = [
    MainTestCase(
        description="returns parser error for command local debug",
        argv=["build", "--debug"],
        expected_exit_code=2,
    ),
    MainTestCase(
        description="returns parser error for command local no color",
        argv=["plan", "--no-color"],
        expected_exit_code=2,
    ),
]

SCENARIO_NO_SQL_VALIDATION_FLAG_ERROR_TEST_CASES: list[MainTestCase] = [
    MainTestCase(
        description="rejects no sql validation flag on scenario test",
        argv=["scenario", "test", "order_totals_pass", "--no-sql-validation"],
        expected_exit_code=2,
    ),
    MainTestCase(
        description="rejects no sql validation flag on scenario capture",
        argv=["scenario", "capture", "order_totals_pass", "--no-sql-validation"],
        expected_exit_code=2,
    ),
]

COMPILE_DISPATCH_TEST_CASES: list[MainTestCase] = [
    MainTestCase(
        description="passes no sql validation flag to compile handler",
        argv=["compile", "--no-sql-validation"],
        expected_exit_code=3,
        expected_project_dir=None,
        expected_no_sql_validation=True,
    ),
    MainTestCase(
        description="passes manifest flag to compile handler",
        argv=["compile", "--manifest"],
        expected_exit_code=3,
        expected_project_dir=None,
        expected_manifest=True,
    ),
    MainTestCase(
        description="passes rich lineage mode to compile handler",
        argv=["compile", "--lineage-mode", "rich"],
        expected_exit_code=3,
        expected_compile_lineage_mode=CompileLineageMode.RICH,
    ),
    MainTestCase(
        description="passes none lineage mode to compile handler",
        argv=["compile", "--lineage-mode", "none"],
        expected_exit_code=3,
        expected_compile_lineage_mode=CompileLineageMode.NONE,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="returns zero for root help",
            argv=["--help"],
            expected_exit_code=0,
        )
    ],
    ids=["returns zero for root help"],
)
def test_given_root_help_arguments_when_running_main_then_it_returns_expected_exit_code(
    test_case: MainTestCase,
) -> None:
    exit_code: int = main(test_case.argv)

    assert exit_code == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches compile command through injected handler",
            argv=["--project-dir", "/tmp/demo", "compile"],
            expected_exit_code=7,
        )
    ],
    ids=["dispatches compile command through injected handler"],
)
def test_given_compile_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(
            run_compile=lambda *_a, **_k: test_case.expected_exit_code,
        ),
    )

    assert exit_code == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches dbt plan and preserves dbt args",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "--no-color",
                "dbt",
                "plan",
                "--json",
                "--select",
                "path:models/marts",
                "--project-dir",
                "dbt_project",
                "--sqb-start-cursor-int",
                "10",
            ],
            expected_exit_code=13,
            expected_project_dir=Path("/tmp/demo"),
            expected_no_color=True,
            expected_dbt_args=(
                "--json",
                "--select",
                "path:models/marts",
                "--project-dir",
                "dbt_project",
                "--sqb-start-cursor-int",
                "10",
            ),
        )
    ],
    ids=["dispatches dbt plan and preserves dbt args"],
)
def test_given_dbt_plan_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, tuple[str, ...], bool]] = []

    def run_dbt_plan(
        project_dir: Path | None,
        args: tuple[str, ...],
        no_color: bool,
    ) -> int:
        received_args.append((project_dir, args, no_color))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_dbt_plan=run_dbt_plan),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (test_case.expected_project_dir, test_case.expected_dbt_args, test_case.expected_no_color)
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="rejects dbt without subcommand",
            argv=["dbt"],
            expected_exit_code=1,
        )
    ],
    ids=["rejects dbt without subcommand"],
)
def test_given_dbt_without_subcommand_when_running_with_dependencies_then_it_returns_cli_error(
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(),
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code
    assert "error[C237]: dbt requires a subcommand such as 'plan'" in captured.err


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches clone command through injected handler",
            argv=["clone", "--from", "prod", "--to", "dev", "--select", "orders"],
            expected_exit_code=8,
        )
    ],
    ids=["dispatches clone command through injected handler"],
)
def test_given_clone_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[Path | None, bool, bool, str, str, bool, tuple[str, ...], tuple[str, ...]]
    ] = []

    def run_clone(
        project_dir: Path | None,
        no_color: bool,
        no_sql_validation: bool,
        from_environment: str,
        to_environment: str,
        hard_copy: bool,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
    ) -> int:
        received_args.append(
            (
                project_dir,
                no_color,
                no_sql_validation,
                from_environment,
                to_environment,
                hard_copy,
                select,
                exclude,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_clone=run_clone),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [(None, False, False, "prod", "dev", False, ("orders",), ())]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches diff command through injected handler",
            argv=["diff", "prod:dev", "--full", "--select", "orders"],
            expected_exit_code=6,
        )
    ],
    ids=["dispatches diff command through injected handler"],
)
def test_given_diff_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            bool,
            bool,
            str,
            str,
            bool,
            bool,
            str | None,
            int | None,
            int | None,
            tuple[str, ...],
            tuple[str, ...],
            bool,
        ]
    ] = []

    def run_diff(
        project_dir: Path | None,
        no_color: bool,
        no_sql_validation: bool,
        from_environment: str,
        to_environment: str,
        full: bool,
        schema_only: bool,
        bounded: str | None,
        max_column_examples: int | None,
        max_row_only_examples: int | None,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        verbose: bool,
    ) -> int:
        received_args.append(
            (
                project_dir,
                no_color,
                no_sql_validation,
                from_environment,
                to_environment,
                full,
                schema_only,
                bounded,
                max_column_examples,
                max_row_only_examples,
                select,
                exclude,
                verbose,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_diff=run_diff),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (None, False, False, "prod", "dev", True, False, None, None, None, ("orders",), (), False)
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches scenario test with multiple selectors and local snapshot sync",
            argv=[
                "scenario",
                "test",
                "order_totals_pass",
                "tests/scenarios/nested",
                "--local",
                "--strict",
                "--sync-snapshots",
                "--force",
                "--max-snapshot-rows",
                "7",
            ],
            expected_exit_code=5,
            expected_scenario_selectors=("order_totals_pass", "tests/scenarios/nested"),
        )
    ],
    ids=["dispatches scenario test with multiple selectors"],
)
def test_given_scenario_test_arguments_when_running_with_dependencies_then_dispatches_selectors(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            bool,
            bool,
            tuple[str, ...],
            bool,
            bool,
            bool,
            bool,
            bool,
            bool,
            int | None,
            int | None,
            int | None,
            int | None,
        ]
    ] = []

    def run_scenario(
        project_dir: Path | None,
        no_sql_validation: bool,
        no_color: bool,
        selectors: tuple[str, ...],
        retain: bool,
        local: bool,
        strict: bool,
        sync_snapshots: bool,
        refresh: bool,
        force: bool,
        max_snapshot_rows: int | None,
        max_snapshot_total_rows: int | None,
        max_snapshot_bytes: int | None,
        max_snapshot_total_bytes: int | None,
    ) -> int:
        received_args.append(
            (
                project_dir,
                no_sql_validation,
                no_color,
                selectors,
                retain,
                local,
                strict,
                sync_snapshots,
                refresh,
                force,
                max_snapshot_rows,
                max_snapshot_total_rows,
                max_snapshot_bytes,
                max_snapshot_total_bytes,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_scenario=run_scenario),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (
            None,
            False,
            False,
            test_case.expected_scenario_selectors,
            False,
            True,
            True,
            True,
            False,
            True,
            7,
            None,
            None,
            None,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="rejects local scenario retain flag",
            argv=["scenario", "test", "order_totals_pass", "--local", "--retain"],
            expected_exit_code=1,
        )
    ],
    ids=["rejects local scenario retain flag"],
)
def test_given_local_scenario_test_with_retain_when_running_then_returns_cli_error(
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(),
    )
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert "error[C452]: scenario test --local does not support --retain" in rendered_stderr
    assert (
        "Local scenario DuckDB files are always kept under target/run/scenarios/."
        in rendered_stderr
    )


@pytest.mark.parametrize(
    "test_case",
    SCENARIO_NO_SQL_VALIDATION_FLAG_ERROR_TEST_CASES,
    ids=[case.description for case in SCENARIO_NO_SQL_VALIDATION_FLAG_ERROR_TEST_CASES],
)
def test_given_scenario_command_when_no_sql_validation_flag_passed_then_parser_rejects_it(
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(),
    )
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert "unrecognized arguments: --no-sql-validation" in rendered_stderr


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches scenario capture with multiple selectors",
            argv=[
                "scenario",
                "capture",
                "order_totals_pass",
                "tests/scenarios/nested",
                "--retain",
                "--max-snapshot-total-rows",
                "9",
            ],
            expected_exit_code=6,
            expected_scenario_selectors=("order_totals_pass", "tests/scenarios/nested"),
        )
    ],
    ids=["dispatches scenario capture with multiple selectors"],
)
def test_given_scenario_capture_arguments_when_running_with_dependencies_then_dispatches_selectors(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            bool,
            bool,
            tuple[str, ...],
            bool,
            bool,
            int | None,
            int | None,
            int | None,
            int | None,
        ]
    ] = []

    def run_scenario_capture(
        project_dir: Path | None,
        no_sql_validation: bool,
        no_color: bool,
        selectors: tuple[str, ...],
        retain: bool,
        force: bool,
        max_snapshot_rows: int | None,
        max_snapshot_total_rows: int | None,
        max_snapshot_bytes: int | None,
        max_snapshot_total_bytes: int | None,
    ) -> int:
        received_args.append(
            (
                project_dir,
                no_sql_validation,
                no_color,
                selectors,
                retain,
                force,
                max_snapshot_rows,
                max_snapshot_total_rows,
                max_snapshot_bytes,
                max_snapshot_total_bytes,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_scenario_capture=run_scenario_capture),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (
            None,
            False,
            False,
            test_case.expected_scenario_selectors,
            True,
            False,
            None,
            9,
            None,
            None,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches query command through injected handler",
            argv=[
                "query",
                "select 1 as id",
                "--format",
                "table",
                "--limit",
                "5",
            ],
            expected_exit_code=4,
        )
    ],
    ids=["dispatches query command through injected handler"],
)
def test_given_query_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, str | None, str, int | None]] = []

    def run_query(
        project_dir: Path | None,
        sql: str | None,
        output_format: str,
        limit: int | None,
    ) -> int:
        received_args.append((project_dir, sql, output_format, limit))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_query=run_query),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [(None, "select 1 as id", "table", 5)]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches debug command through injected handler",
            argv=["--no-color", "debug", "--no-connection", "--json"],
            expected_exit_code=12,
            expected_no_color=True,
        )
    ],
    ids=["dispatches debug command through injected handler"],
)
def test_given_debug_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, bool, bool, bool]] = []

    def run_debug(
        project_dir: Path | None,
        no_color: bool,
        no_connection: bool,
        json_output: bool,
    ) -> int:
        received_args.append((project_dir, no_color, no_connection, json_output))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_debug=run_debug),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [(None, True, True, True)]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches lineage command through injected handler",
            argv=[
                "lineage",
                "fact_orders",
                "--direction",
                "both",
                "--depth",
                "2",
                "--format",
                "json",
                "--mode",
                "fast",
            ],
            expected_exit_code=11,
            expected_column_lineage_mode=ColumnLineageMode.FAST,
        )
    ],
    ids=["dispatches lineage command through injected handler"],
)
def test_given_lineage_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            bool,
            str | None,
            str,
            str,
            str,
            tuple[str, ...],
            tuple[str, ...],
            ColumnLineageMode,
        ]
    ] = []

    def run_lineage(
        project_dir: Path | None,
        no_sql_validation: bool,
        target: str | None,
        output_format: str,
        direction: str,
        depth: str,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        lineage_mode: ColumnLineageMode,
    ) -> int:
        received_args.append(
            (
                project_dir,
                no_sql_validation,
                target,
                output_format,
                direction,
                depth,
                select,
                exclude,
                lineage_mode,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_lineage=run_lineage),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (
            None,
            False,
            "fact_orders",
            "json",
            "both",
            "2",
            (),
            (),
            test_case.expected_column_lineage_mode,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes verbose flag to diff handler",
            argv=[
                "diff",
                "prod:dev",
                "--full",
                "--verbose",
                "--select",
                "orders",
            ],
            expected_exit_code=6,
        )
    ],
    ids=["passes verbose flag to diff handler"],
)
def test_given_verbose_diff_arguments_when_running_then_it_dispatches_verbose_flag(
    test_case: MainTestCase,
) -> None:
    received_verbose: list[bool] = []

    def run_diff(
        project_dir: Path | None,
        no_color: bool,
        no_sql_validation: bool,
        from_environment: str,
        to_environment: str,
        full: bool,
        schema_only: bool,
        bounded: str | None,
        max_column_examples: int | None,
        max_row_only_examples: int | None,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        verbose: bool,
    ) -> int:
        del project_dir, no_color, no_sql_validation, from_environment, to_environment, full
        del schema_only, bounded, max_column_examples, max_row_only_examples, select, exclude
        received_verbose.append(verbose)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_diff=run_diff),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_verbose == [True]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes diff example caps to handler",
            argv=[
                "diff",
                "prod:dev",
                "--full",
                "--max-column-examples",
                "7",
                "--max-row-only-examples",
                "4",
                "--select",
                "orders",
            ],
            expected_exit_code=6,
        )
    ],
    ids=["passes diff example caps to handler"],
)
def test_given_diff_example_cap_arguments_when_running_then_it_dispatches_caps(
    test_case: MainTestCase,
) -> None:
    received_caps: list[tuple[int | None, int | None]] = []

    def run_diff(
        project_dir: Path | None,
        no_color: bool,
        no_sql_validation: bool,
        from_environment: str,
        to_environment: str,
        full: bool,
        schema_only: bool,
        bounded: str | None,
        max_column_examples: int | None,
        max_row_only_examples: int | None,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        verbose: bool,
    ) -> int:
        del project_dir, no_color, no_sql_validation, from_environment, to_environment, full
        del schema_only, bounded, select, exclude, verbose
        received_caps.append((max_column_examples, max_row_only_examples))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_diff=run_diff),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_caps == [(7, 4)]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches janitor command through injected handler",
            argv=["--no-color", "janitor", "--auto-approve", "--retention-days", "0"],
            expected_exit_code=9,
            expected_no_color=True,
        )
    ],
    ids=["dispatches janitor command through injected handler"],
)
def test_given_janitor_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, bool, bool, int | None]] = []

    def run_janitor(
        project_dir: Path | None,
        no_color: bool,
        auto_approve: bool,
        retention_days: int | None,
    ) -> int:
        received_args.append((project_dir, no_color, auto_approve, retention_days))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_janitor=run_janitor),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [(None, test_case.expected_no_color, True, 0)]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches playground command through injected handler",
            argv=["--project-dir", "/tmp/demo", "playground", "shop"],
            expected_exit_code=5,
            expected_project_dir=Path("/tmp/demo"),
        )
    ],
    ids=["dispatches playground command through injected handler"],
)
def test_given_playground_command_when_running_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, str]] = []

    def run_playground(project_dir: Path | None, playground_path: str) -> int:
        received_args.append((project_dir, playground_path))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_playground=run_playground),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [(test_case.expected_project_dir, "shop")]


@pytest.mark.parametrize(
    "test_case",
    COMPILE_DISPATCH_TEST_CASES,
    ids=[case.description for case in COMPILE_DISPATCH_TEST_CASES],
)
def test_given_compile_no_sql_validation_when_running_then_dispatches_expected_flag(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[Path | None, bool, str | None, bool, bool, bool, CompileLineageMode]
    ] = []

    def run_compile(
        project_dir: Path | None,
        no_sql_validation: bool,
        defer_to: str | None,
        json_output: bool,
        manifest: bool,
        no_color: bool,
        lineage_mode: CompileLineageMode,
    ) -> int:
        received_args.append(
            (
                project_dir,
                no_sql_validation,
                defer_to,
                json_output,
                manifest,
                no_color,
                lineage_mode,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_compile=run_compile),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (
            test_case.expected_project_dir,
            test_case.expected_no_sql_validation,
            None,
            False,
            test_case.expected_manifest,
            False,
            test_case.expected_compile_lineage_mode,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes global debug and no color plus full refresh to build handler",
            argv=["--debug", "--no-color", "build", "--full-refresh"],
            expected_exit_code=5,
            expected_full_refresh=True,
            expected_no_color=True,
            expected_debug=True,
        )
    ],
    ids=["passes global debug and no color plus full refresh to build handler"],
)
def test_given_build_full_refresh_when_running_then_dispatches_expected_flag(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[bool, bool, bool, bool]] = []

    def run_build(
        project_dir: Path | None,
        no_sql_validation: bool,
        defer_to: str | None,
        cursor_overrides: object,
        no_color: bool,
        fail_fast: bool,
        full_refresh: bool,
        concurrency: int | None,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        verbose: bool = False,
        debug: bool = False,
    ) -> int:
        del project_dir
        del no_sql_validation
        del defer_to
        del cursor_overrides
        del concurrency
        del select
        del exclude
        del verbose
        received_args.append((no_color, fail_fast, full_refresh, debug))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_build=run_build),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (
            test_case.expected_no_color,
            False,
            test_case.expected_full_refresh,
            test_case.expected_debug,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes full refresh flag to run handler",
            argv=["run", "--full-refresh"],
            expected_exit_code=6,
            expected_full_refresh=True,
        )
    ],
    ids=["passes full refresh flag to run handler"],
)
def test_given_run_full_refresh_when_running_then_dispatches_expected_flag(
    test_case: MainTestCase,
) -> None:
    received_args: list[bool] = []

    def run_run(
        project_dir: Path | None,
        no_sql_validation: bool,
        defer_to: str | None,
        cursor_overrides: object,
        no_color: bool,
        fail_fast: bool,
        full_refresh: bool,
        concurrency: int | None,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        verbose: bool = False,
        debug: bool = False,
    ) -> int:
        del project_dir
        del no_sql_validation
        del defer_to
        del cursor_overrides
        del no_color
        del fail_fast
        del concurrency
        del select
        del exclude
        del verbose
        del debug
        received_args.append(full_refresh)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_run=run_run),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [test_case.expected_full_refresh]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes global no color to plan handler",
            argv=["--no-color", "plan", "--select", "orders", "--exclude", "customers"],
            expected_exit_code=4,
            expected_no_color=True,
        )
    ],
    ids=["passes global no color to plan handler"],
)
def test_given_plan_flags_when_running_then_dispatches_expected_arguments(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            bool,
            str | None,
            object,
            bool,
            bool,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            bool,
        ]
    ] = []

    def run_plan(
        project_dir: Path | None,
        no_sql_validation: bool,
        defer_to: str | None,
        cursor_overrides: object,
        json_output: bool,
        full_refresh: bool,
        no_color: bool,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        verbose: bool,
    ) -> int:
        received_args.append(
            (
                project_dir,
                no_sql_validation,
                defer_to,
                cursor_overrides,
                json_output,
                full_refresh,
                no_color,
                select,
                exclude,
                verbose,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_plan=run_plan),
    )

    assert exit_code == test_case.expected_exit_code
    assert len(received_args) == 1
    assert received_args[0][4:] == (
        False,
        False,
        test_case.expected_no_color,
        ("orders",),
        ("customers",),
        False,
    )


@pytest.mark.parametrize(
    "test_case",
    COMMAND_LOCAL_GLOBAL_FLAG_ERROR_TEST_CASES,
    ids=[case.description for case in COMMAND_LOCAL_GLOBAL_FLAG_ERROR_TEST_CASES],
)
def test_given_command_local_global_flags_when_running_main_then_it_returns_parser_error(
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code: int = main(test_case.argv)
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert "error[C900]:" in rendered_stderr


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="colorizes parser error prefix when color is supported",
            argv=["build", "--debug"],
            expected_exit_code=2,
        )
    ],
    ids=["colorizes parser error prefix when color is supported"],
)
def test_given_parser_error_and_color_support_when_running_main_then_it_colorizes_error_prefix(
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sqlbuild.cli.commands.main.entry.supports_color", lambda: True)

    exit_code: int = main(test_case.argv)
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert "\033[31m\033[1merror[C900]:\033[0m" in rendered_stderr


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="leaves parser error plain when no color is requested",
            argv=["--no-color", "build", "--debug"],
            expected_exit_code=2,
        )
    ],
    ids=["leaves parser error plain when no color is requested"],
)
def test_given_parser_error_and_no_color_when_running_main_then_it_renders_plain_error_prefix(
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sqlbuild.cli.commands.main.entry.supports_color", lambda: True)

    exit_code: int = main(test_case.argv)
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert "error[C900]:" in rendered_stderr
    assert "\033[31m" not in rendered_stderr


@pytest.mark.parametrize(
    "test_case",
    ERROR_RENDERING_TEST_CASES,
    ids=[case.description for case in ERROR_RENDERING_TEST_CASES],
)
def test_given_expected_cli_errors_when_running_main_then_it_renders_stderr_and_returns_one(
    test_case: MainErrorRenderingTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_compile(
        project_dir: Path | None,
        no_sql_validation: bool,
        defer_to: str | None,
        json_output: bool,
        manifest: bool,
        no_color: bool,
        lineage_mode: CompileLineageMode,
    ) -> int:
        del no_sql_validation
        del defer_to
        del json_output
        del manifest
        del no_color
        del lineage_mode
        assert project_dir is not None
        raise test_case.error_factory(project_dir)

    def run_query(
        project_dir: Path | None,
        sql: str | None,
        output_format: str,
        limit: int | None,
    ) -> int:
        del project_dir, sql, output_format, limit
        raise test_case.error_factory(Path("/tmp/demo"))

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_compile=run_compile, run_query=run_query),
    )
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in rendered_stderr


@pytest.mark.parametrize(
    "test_case",
    [
        MainErrorRenderingTestCase(
            description="colorizes expected cli error prefix and help label",
            argv=["query", "SELECT 1"],
            error_type=CliUserError,
            error_factory=lambda project_dir: CliUserError(
                "query requires SQL",
                code="C102",
                help="pass SQL as the query argument",
            ),
            expected_stderr_fragment=(
                "\033[31m\033[1merror[C102]:\033[0m query requires SQL\n"
                "  \033[2m= help:\033[0m pass SQL as the query argument"
            ),
            expected_exit_code=1,
        )
    ],
    ids=["colorizes expected cli error prefix and help label"],
)
def test_given_expected_cli_error_and_color_support_when_running_main_then_it_colorizes_stderr(
    test_case: MainErrorRenderingTestCase,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sqlbuild.cli.commands.main.entry.supports_color", lambda: True)

    def run_query(
        project_dir: Path | None,
        sql: str | None,
        output_format: str,
        limit: int | None,
    ) -> int:
        del project_dir, sql, output_format, limit
        raise test_case.error_factory(Path("/tmp/demo"))

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_query=run_query),
    )
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in rendered_stderr
