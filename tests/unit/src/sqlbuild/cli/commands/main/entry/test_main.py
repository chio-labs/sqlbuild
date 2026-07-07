from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.helpers.build.models import BuildCommandRequest
from sqlbuild.cli.commands.helpers.clone.models import CloneCommandRequest
from sqlbuild.cli.commands.helpers.compile.models import CompileCommandRequest
from sqlbuild.cli.commands.helpers.compile.types import CompileLineageMode
from sqlbuild.cli.commands.helpers.dbt_init.models import DbtInitCommandRequest
from sqlbuild.cli.commands.helpers.diff.models import DiffCommandRequest
from sqlbuild.cli.commands.helpers.freshness.models import FreshnessCommandRequest
from sqlbuild.cli.commands.helpers.janitor.models import JanitorCommandRequest
from sqlbuild.cli.commands.helpers.load.models import LoadCommandRequest
from sqlbuild.cli.commands.helpers.plan.models import PlanCommandRequest
from sqlbuild.cli.commands.helpers.playground.models import PlaygroundCommandRequest
from sqlbuild.cli.commands.helpers.promote.models import PromoteCommandRequest
from sqlbuild.cli.commands.helpers.rollback.models import RollbackCommandRequest
from sqlbuild.cli.commands.helpers.scenario.models import (
    ScenarioCaptureCommandRequest,
    ScenarioTestCommandRequest,
)
from sqlbuild.cli.commands.main.commands.entry import _main_with_dependencies, main
from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.planner.models import CursorOverrides
from tests.unit.src.sqlbuild.cli.commands.main.entry._test_types import (
    MainErrorRenderingTestCase,
    MainTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.entry.helpers import (
    build_handlers,
    build_json_recording_handler,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="returns zero for root help",
            argv=["--help"],
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
                "--start-cursor-int",
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
                "--start-cursor-int",
                "10",
            ),
        )
    ],
    ids=lambda case: case.description,
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
            description="dbt command does not create diagnostics target before auto-init",
            argv=["dbt", "plan"],
            expected_exit_code=41,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_command_without_sqlbuild_project_when_dispatching_then_does_not_create_target(
    test_case: MainTestCase,
    tmp_path: Path,
) -> None:
    raw_dbt_dir: Path = tmp_path / "raw_dbt_project"
    received_project_dirs: list[Path | None] = []

    def run_dbt_plan(project_dir: Path | None, args: tuple[str, ...], no_color: bool) -> int:
        del args, no_color
        received_project_dirs.append(project_dir)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=["--project-dir", raw_dbt_dir.as_posix(), *test_case.argv],
        handlers=build_handlers(run_dbt_plan=run_dbt_plan),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_project_dirs == [raw_dbt_dir]
    assert not (raw_dbt_dir / "target").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches dbt run and preserves dbt args",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "dbt",
                "run",
                "--select",
                "tag:nightly",
                "--start-cursor-int",
                "10",
            ],
            expected_exit_code=17,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=("--select", "tag:nightly", "--start-cursor-int", "10"),
        ),
        MainTestCase(
            description="dispatches dbt build and preserves dbt args",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "dbt",
                "build",
                "--select",
                "tag:nightly",
            ],
            expected_exit_code=19,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=("--select", "tag:nightly"),
        ),
        MainTestCase(
            description="dispatches dbt build with sqb project dir alias",
            argv=[
                "--sqb-project-dir",
                "/tmp/demo",
                "dbt",
                "build",
                "--project-dir",
                "dbt_project",
            ],
            expected_exit_code=19,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=("--project-dir", "dbt_project"),
        ),
        MainTestCase(
            description="dispatches dbt plan with sqb project dir alias and dbt flags",
            argv=[
                "--sqb-project-dir",
                "/tmp/demo",
                "dbt",
                "plan",
                "--project-dir",
                "dbt_project",
                "--profiles-dir",
                "profiles",
                "--target",
                "dev",
                "--select",
                "dbt_orders",
            ],
            expected_exit_code=16,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=(
                "--project-dir",
                "dbt_project",
                "--profiles-dir",
                "profiles",
                "--target",
                "dev",
                "--select",
                "dbt_orders",
            ),
        ),
        MainTestCase(
            description="dispatches dbt test and preserves dbt args",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "dbt",
                "test",
                "--select",
                "test_type:data",
                "--indirect-selection",
                "eager",
            ],
            expected_exit_code=23,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=("--select", "test_type:data", "--indirect-selection", "eager"),
        ),
        MainTestCase(
            description="dispatches dbt debug and preserves dbt args",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "dbt",
                "debug",
                "--project-dir",
                "dbt_project",
                "--profiles-dir",
                "profiles",
                "--no-connection",
            ],
            expected_exit_code=29,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=(
                "--project-dir",
                "dbt_project",
                "--profiles-dir",
                "profiles",
                "--no-connection",
            ),
        ),
        MainTestCase(
            description="dispatches dbt debug with sqb project dir alias",
            argv=[
                "--sqb-project-dir",
                "/tmp/demo",
                "dbt",
                "debug",
                "--project-dir",
                "dbt_project",
                "--profiles-dir",
                "profiles",
            ],
            expected_exit_code=29,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=(
                "--project-dir",
                "dbt_project",
                "--profiles-dir",
                "profiles",
            ),
        ),
        MainTestCase(
            description="dispatches dbt lineage and preserves dbt args",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "dbt",
                "lineage",
                "downstream_orders",
                "--format",
                "json",
                "--project-dir",
                "dbt_project",
            ],
            expected_exit_code=31,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=(
                "downstream_orders",
                "--format",
                "json",
                "--project-dir",
                "dbt_project",
            ),
        ),
        MainTestCase(
            description="dispatches dbt diff and preserves dbt args",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "dbt",
                "diff",
                "--select",
                "dbt_orders",
                "--full",
                "--target",
                "prod",
            ],
            expected_exit_code=41,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=("--select", "dbt_orders", "--full", "--target", "prod"),
        ),
        MainTestCase(
            description="dispatches dbt diff with sqb project dir alias",
            argv=[
                "--sqb-project-dir",
                "/tmp/demo",
                "dbt",
                "diff",
                "--select",
                "dbt_orders",
                "--schema-only",
            ],
            expected_exit_code=41,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=("--select", "dbt_orders", "--schema-only"),
        ),
        MainTestCase(
            description="dispatches dbt clone and preserves dbt args",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "dbt",
                "clone",
                "--select",
                "dbt_orders",
                "--hard-copy",
                "--target",
                "dev",
            ],
            expected_exit_code=43,
            expected_project_dir=Path("/tmp/demo"),
            expected_dbt_args=("--select", "dbt_orders", "--hard-copy", "--target", "dev"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_execution_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, tuple[str, ...], bool]] = []

    def run_dbt_execution(
        project_dir: Path | None,
        args: tuple[str, ...],
        no_color: bool,
    ) -> int:
        received_args.append((project_dir, args, no_color))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(
            run_dbt_plan=run_dbt_execution,
            run_dbt_run=run_dbt_execution,
            run_dbt_build=run_dbt_execution,
            run_dbt_test=run_dbt_execution,
            run_dbt_debug=run_dbt_execution,
            run_dbt_lineage=run_dbt_execution,
            run_dbt_diff=run_dbt_execution,
            run_dbt_clone=run_dbt_execution,
        ),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (test_case.expected_project_dir, test_case.expected_dbt_args, test_case.expected_no_color)
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches dbt init options including production git ref",
            argv=[
                "--project-dir",
                "/tmp/workspace",
                "dbt",
                "init",
                "--project-dir",
                "dbt_project",
                "--profiles-dir",
                "profiles",
                "--profile",
                "analytics_profile",
                "--target",
                "dev",
                "--sqb-output-dir",
                "sqlbuild_project",
                "--dry-run",
                "--overwrite",
                "--skip-dbt-debug",
                "--prod-git-ref",
                "prod",
            ],
            expected_exit_code=37,
            expected_project_dir=Path("/tmp/workspace"),
            expected_dbt_init_project_dir="dbt_project",
            expected_dbt_init_profiles_dir="profiles",
            expected_dbt_init_profile_name="analytics_profile",
            expected_dbt_init_target_name="dev",
            expected_dbt_init_sqb_output_dir="sqlbuild_project",
            expected_dbt_init_dry_run=True,
            expected_dbt_init_overwrite=True,
            expected_dbt_init_skip_dbt_debug=True,
            expected_dbt_init_production_git_ref="prod",
        ),
        MainTestCase(
            description="dispatches minimal dbt init with default optional flags",
            argv=["dbt", "init", "--project-dir", "dbt_project"],
            expected_exit_code=38,
            expected_project_dir=Path.cwd(),
            expected_dbt_init_project_dir="dbt_project",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_init_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[DbtInitCommandRequest] = []

    def run_dbt_init(request: DbtInitCommandRequest) -> int:
        received_args.append(request)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_dbt_init=run_dbt_init),
    )

    assert test_case.expected_project_dir is not None
    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        DbtInitCommandRequest(
            cwd=test_case.expected_project_dir,
            dbt_project_dir=test_case.expected_dbt_init_project_dir,
            profiles_dir=test_case.expected_dbt_init_profiles_dir,
            profile_name=test_case.expected_dbt_init_profile_name,
            target_name=test_case.expected_dbt_init_target_name,
            sqb_output_dir=test_case.expected_dbt_init_sqb_output_dir,
            dry_run=test_case.expected_dbt_init_dry_run,
            overwrite=test_case.expected_dbt_init_overwrite,
            skip_dbt_debug=test_case.expected_dbt_init_skip_dbt_debug,
            production_git_ref=test_case.expected_dbt_init_production_git_ref,
        )
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
    ids=lambda case: case.description,
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
            argv=[
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--select",
                "orders",
                "--virtual-env",
                "preview",
                "--skip-locked",
                "--verbose",
            ],
            expected_exit_code=8,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[CloneCommandRequest] = []

    def run_clone(request: CloneCommandRequest) -> int:
        received_args.append(request)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_clone=run_clone),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        CloneCommandRequest(
            project_dir=None,
            no_color=False,
            no_sql_validation=False,
            origin_target_name="prod",
            destination_target_name="dev",
            hard_copy=False,
            virtual_env="preview",
            skip_locked=True,
            select=("orders",),
            exclude=(),
            verbose=True,
            cli_vars={},
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches diff command through injected handler",
            argv=[
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "orders",
                "--allow-partial-diff",
            ],
            expected_exit_code=6,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_diff_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[DiffCommandRequest] = []

    def run_diff(request: DiffCommandRequest) -> int:
        received_args.append(request)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_diff=run_diff),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        DiffCommandRequest(
            project_dir=None,
            no_color=False,
            no_sql_validation=False,
            from_name="prod",
            to_name="dev",
            full=True,
            schema_only=False,
            bounded=None,
            max_column_examples=None,
            max_row_only_examples=None,
            select=("orders",),
            exclude=(),
            verbose=False,
            cli_vars={},
            allow_partial_diff=True,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches promote command through injected handler",
            argv=[
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
                "--verbose",
            ],
            expected_exit_code=7,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_promote_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            bool,
            bool,
            str,
            str,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            bool,
            bool,
        ]
    ] = []

    def run_promote(request: PromoteCommandRequest) -> int:
        received_args.append(
            (
                request.project_dir,
                request.no_color,
                request.no_sql_validation,
                request.from_virtual_environment,
                request.to_virtual_environment,
                request.select,
                request.exclude,
                request.allow_partial_promotion,
                request.include_stale_upstreams,
                request.verbose,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_promote=run_promote),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (None, False, False, "pr", "dev", ("fact_orders",), (), True, True, True)
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches rollback command through injected handler",
            argv=[
                "rollback",
                "--virtual-env",
                "dev",
                "--checkpoint-id",
                "chk_1",
                "--select",
                "fact_orders",
                "--allow-partial-rollback",
                "--include-stale-upstreams",
                "--verbose",
            ],
            expected_exit_code=7,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rollback_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            bool,
            bool,
            str | None,
            bool,
            str | None,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            bool,
        ]
    ] = []

    def run_rollback(request: RollbackCommandRequest) -> int:
        received_args.append(
            (
                request.project_dir,
                request.no_color,
                request.no_sql_validation,
                request.virtual_environment,
                request.verbose,
                request.checkpoint_id,
                request.select,
                request.exclude,
                request.allow_partial_rollback,
                request.include_stale_upstreams,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_rollback=run_rollback),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (None, False, False, "dev", True, "chk_1", ("fact_orders",), (), True, True)
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
                "--select",
                "tests/scenarios/nested",
                "--exclude",
                "tests/scenarios/slow",
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
    ids=lambda case: case.description,
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
            bool,
            Path | None,
        ]
    ] = []

    def run_scenario(request: ScenarioTestCommandRequest) -> int:
        received_args.append(
            (
                request.project_dir,
                request.no_sql_validation,
                request.no_color,
                request.selectors,
                request.exclude,
                request.retain,
                request.local,
                request.strict,
                request.sync_snapshots,
                request.refresh,
                request.limit_inputs.force,
                request.limit_inputs.max_snapshot_rows,
                request.limit_inputs.max_snapshot_total_rows,
                request.limit_inputs.max_snapshot_bytes,
                request.limit_inputs.max_snapshot_total_bytes,
                request.json_output,
                request.json_output_path,
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
            ("tests/scenarios/slow",),
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
            False,
            None,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches build json flag",
            argv=["build", "--json"],
            expected_exit_code=0,
            expected_json=True,
        ),
        MainTestCase(
            description="dispatches test json flag",
            argv=["test", "--json"],
            expected_exit_code=0,
            expected_json=True,
        ),
        MainTestCase(
            description="dispatches audit json flag",
            argv=["audit", "--json"],
            expected_exit_code=0,
            expected_json=True,
        ),
        MainTestCase(
            description="dispatches seed json flag",
            argv=["seed", "--json"],
            expected_exit_code=0,
            expected_json=True,
        ),
        MainTestCase(
            description="dispatches load json flag",
            argv=["load", "--json"],
            expected_exit_code=0,
            expected_json=True,
        ),
        MainTestCase(
            description="dispatches scenario test json flag",
            argv=["scenario", "test", "daily", "--json"],
            expected_exit_code=0,
            expected_json=True,
        ),
        MainTestCase(
            description="dispatches build json output path",
            argv=["build", "--json-output", "target/execution.json"],
            expected_exit_code=0,
            expected_json_output_path=Path("target/execution.json"),
        ),
        MainTestCase(
            description="dispatches scenario test json output path",
            argv=["scenario", "test", "daily", "--json-output", "target/scenario.json"],
            expected_exit_code=0,
            expected_json_output_path=Path("target/scenario.json"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_execution_command_json_flag_when_running_then_dispatches_json_output(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[bool, Path | None]] = []
    record_json_handler: Callable[..., int] = build_json_recording_handler(
        received_args=received_args,
        exit_code=test_case.expected_exit_code,
    )

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(
            run_build=record_json_handler,
            run_test=record_json_handler,
            run_audit=record_json_handler,
            run_seed=record_json_handler,
            run_load=record_json_handler,
            run_scenario=record_json_handler,
        ),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [(test_case.expected_json, test_case.expected_json_output_path)]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes freshness flags to handler",
            argv=[
                "freshness",
                "--no-sql-validation",
                "--select",
                "raw_orders",
                "raw_payments",
                "--exclude",
                "raw_events",
                "--vars",
                '{"tenant":"acme"}',
                "--fail-on-error",
                "--state",
                "--virtual-env",
                "dev",
                "--fail-on-stale",
            ],
            expected_exit_code=8,
            expected_no_sql_validation=True,
            expected_select=("raw_orders", "raw_payments"),
            expected_vars={"tenant": "acme"},
            expected_fail_on_error=True,
            expected_state=True,
            expected_fail_on_stale=True,
            expected_virtual_env="dev",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_freshness_arguments_when_running_then_dispatches_expected_arguments(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            bool,
            tuple[str, ...],
            tuple[str, ...],
            dict[str, object] | None,
            bool,
            bool,
            bool,
            str | None,
        ]
    ] = []

    def run_freshness(request: FreshnessCommandRequest) -> int:
        received_args.append(
            (
                request.no_sql_validation,
                request.select,
                request.exclude,
                request.cli_vars,
                request.fail_on_error,
                request.compare_state,
                request.fail_on_stale,
                request.virtual_environment_name,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_freshness=run_freshness),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (
            test_case.expected_no_sql_validation,
            test_case.expected_select,
            ("raw_events",),
            test_case.expected_vars,
            test_case.expected_fail_on_error,
            test_case.expected_state,
            test_case.expected_fail_on_stale,
            test_case.expected_virtual_env,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes freshness json flag",
            argv=["freshness", "--json"],
            expected_exit_code=8,
            expected_json=True,
        ),
        MainTestCase(
            description="passes freshness json output path",
            argv=["freshness", "--json-output", "target/freshness.json"],
            expected_exit_code=8,
            expected_json_output_path=Path("target/freshness.json"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_freshness_json_arguments_when_running_then_dispatches_expected_arguments(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[bool, Path | None]] = []

    def run_freshness(request: FreshnessCommandRequest) -> int:
        received_args.append((request.json_output, request.json_output_path))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_freshness=run_freshness),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [(test_case.expected_json, test_case.expected_json_output_path)]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes load selectors reload flag and cursor overrides to handler",
            argv=[
                "load",
                "--select",
                "raw_orders",
                "--exclude",
                "raw_events",
                "--reload",
                "--start-cursor-ts",
                "2026-01-01T00:00:00",
                "--end-cursor-int",
                "20",
            ],
            expected_exit_code=4,
            expected_select=("raw_orders",),
            expected_reload=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_load_flags_when_running_then_dispatches_expected_arguments(
    test_case: MainTestCase,
) -> None:
    received_args: list[LoadCommandRequest] = []

    def run_load(request: LoadCommandRequest) -> int:
        received_args.append(request)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_load=run_load),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        LoadCommandRequest(
            project_dir=None,
            no_color=False,
            selected_target=None,
            select=test_case.expected_select,
            exclude=("raw_events",),
            reload=test_case.expected_reload,
            concurrency=None,
            cursor_overrides=CursorOverrides(start_ts="2026-01-01T00:00:00", end_int="20"),
            cli_vars={},
            json_output=False,
            json_output_path=None,
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
    ids=lambda case: case.description,
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
    [
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
    ],
    ids=lambda case: case.description,
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
                "--select",
                "tests/scenarios/nested",
                "--exclude",
                "tests/scenarios/slow",
                "--retain",
                "--max-snapshot-total-rows",
                "9",
            ],
            expected_exit_code=6,
            expected_scenario_selectors=("order_totals_pass", "tests/scenarios/nested"),
        )
    ],
    ids=lambda case: case.description,
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
            tuple[str, ...],
            bool,
            bool,
            int | None,
            int | None,
            int | None,
            int | None,
        ]
    ] = []

    def run_scenario_capture(request: ScenarioCaptureCommandRequest) -> int:
        received_args.append(
            (
                request.project_dir,
                request.no_sql_validation,
                request.no_color,
                request.selectors,
                request.exclude,
                request.retain,
                request.limit_inputs.force,
                request.limit_inputs.max_snapshot_rows,
                request.limit_inputs.max_snapshot_total_rows,
                request.limit_inputs.max_snapshot_bytes,
                request.limit_inputs.max_snapshot_total_bytes,
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
            ("tests/scenarios/slow",),
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
    ids=lambda case: case.description,
)
def test_given_query_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, str | None, str, int | None]] = []

    def run_query(
        project_dir: Path | None,
        sql: str | None,
        selected_target: str | None,
        output_format: str,
        limit: int | None,
    ) -> int:
        del selected_target
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
    ids=lambda case: case.description,
)
def test_given_debug_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, bool, bool, bool]] = []

    def run_debug(
        project_dir: Path | None,
        no_color: bool,
        no_connection: bool,
        selected_target: str | None,
        json_output: bool,
    ) -> int:
        del selected_target
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
    ids=lambda case: case.description,
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
        cli_vars: dict[str, object],
    ) -> int:
        del cli_vars
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
    ids=lambda case: case.description,
)
def test_given_verbose_diff_arguments_when_running_then_it_dispatches_verbose_flag(
    test_case: MainTestCase,
) -> None:
    received_verbose: list[bool] = []

    def run_diff(request: DiffCommandRequest) -> int:
        received_verbose.append(request.verbose)
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
    ids=lambda case: case.description,
)
def test_given_diff_example_cap_arguments_when_running_then_it_dispatches_caps(
    test_case: MainTestCase,
) -> None:
    received_caps: list[tuple[int | None, int | None]] = []

    def run_diff(request: DiffCommandRequest) -> int:
        received_caps.append((request.max_column_examples, request.max_row_only_examples))
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
            argv=[
                "--no-color",
                "janitor",
                "--auto-approve",
                "--retention-days",
                "0",
                "--direct-state-history-versions",
                "5",
            ],
            expected_exit_code=9,
            expected_no_color=True,
            expected_direct_state_history_versions=5,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_janitor_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[JanitorCommandRequest] = []

    def run_janitor(request: JanitorCommandRequest) -> int:
        received_args.append(request)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_janitor=run_janitor),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        JanitorCommandRequest(
            project_dir=None,
            no_color=test_case.expected_no_color,
            auto_approve=True,
            retention_days=0,
            direct_state_history_versions=test_case.expected_direct_state_history_versions,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches state rollback command through injected handler",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "--no-color",
                "state",
                "rollback",
                "--backup-id",
                "b1",
            ],
            expected_exit_code=11,
            expected_project_dir=Path("/tmp/demo"),
            expected_no_color=True,
            expected_state_command="rollback",
            expected_state_backup_id="b1",
        ),
        MainTestCase(
            description="dispatches state reset approval through injected handler",
            argv=["state", "reset", "--auto-approve"],
            expected_exit_code=12,
            expected_state_command="reset",
            expected_auto_approve=True,
        ),
        MainTestCase(
            description="dispatches state checkpoints list through injected handler",
            argv=["state", "checkpoints", "list", "--virtual-env", "dev"],
            expected_exit_code=13,
            expected_state_command="checkpoints",
            expected_state_checkpoint_command="list",
            expected_virtual_env="dev",
        ),
        MainTestCase(
            description="dispatches state checkpoints show through injected handler",
            argv=["state", "checkpoints", "show", "chk_1"],
            expected_exit_code=14,
            expected_state_command="checkpoints",
            expected_state_checkpoint_command="show",
            expected_state_checkpoint_id="chk_1",
        ),
        MainTestCase(
            description="dispatches state checkpoints diff through injected handler",
            argv=["state", "checkpoints", "diff", "chk_2", "--virtual-env", "dev"],
            expected_exit_code=15,
            expected_state_command="checkpoints",
            expected_state_checkpoint_command="diff",
            expected_state_checkpoint_id="chk_2",
            expected_virtual_env="dev",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_state_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            str,
            str | None,
            bool,
            bool,
            str | None,
            str | None,
            str | None,
            bool,
        ]
    ] = []

    def run_state(
        project_dir: Path | None,
        state_command: str,
        backup_id: str | None,
        auto_approve: bool,
        no_color: bool,
        checkpoint_command: str | None,
        checkpoint_id: str | None,
        virtual_environment: str | None,
        allow_copy: bool,
    ) -> int:
        received_args.append(
            (
                project_dir,
                state_command,
                backup_id,
                auto_approve,
                no_color,
                checkpoint_command,
                checkpoint_id,
                virtual_environment,
                allow_copy,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_state=run_state),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (
            test_case.expected_project_dir,
            str(test_case.expected_state_command),
            test_case.expected_state_backup_id,
            test_case.expected_auto_approve,
            test_case.expected_no_color,
            test_case.expected_state_checkpoint_command,
            test_case.expected_state_checkpoint_id,
            test_case.expected_virtual_env,
            False,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches playground command through injected handler",
            argv=["--project-dir", "/tmp/demo", "playground", "shop", "--template", "dagster"],
            expected_exit_code=5,
            expected_project_dir=Path("/tmp/demo"),
            expected_playground_template="dagster",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_playground_command_when_running_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, str, str]] = []

    def run_playground(request: PlaygroundCommandRequest) -> int:
        received_args.append((request.project_dir, request.target_path, request.template))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_playground=run_playground),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (test_case.expected_project_dir, "shop", test_case.expected_playground_template)
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="dispatches skills update through injected handler",
            argv=[
                "--project-dir",
                "/tmp/demo",
                "skills",
                "update",
                "--global",
                "--target",
                "opencode",
                "--target",
                "agents",
                "--force",
            ],
            expected_exit_code=31,
            expected_project_dir=Path("/tmp/demo"),
            expected_skills_global=True,
            expected_skills_targets=("opencode", "agents"),
            expected_skills_force=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_skills_update_command_when_running_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, bool, tuple[str, ...], bool]] = []

    def run_skills_update(
        project_dir: Path | None,
        global_install: bool,
        targets: tuple[str, ...],
        force: bool,
    ) -> int:
        received_args.append((project_dir, global_install, targets, force))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_skills_update=run_skills_update),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (
            test_case.expected_project_dir,
            test_case.expected_skills_global,
            test_case.expected_skills_targets,
            test_case.expected_skills_force,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
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
            description="passes dag flag to compile handler",
            argv=["compile", "--dag"],
            expected_exit_code=3,
            expected_project_dir=None,
            expected_dag="",
        ),
        MainTestCase(
            description="passes dag artifact path to compile handler",
            argv=["compile", "--dag", "target/custom_dag.json"],
            expected_exit_code=3,
            expected_project_dir=None,
            expected_dag="target/custom_dag.json",
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
        MainTestCase(
            description="passes sqlbuild vars to compile handler",
            argv=[
                "compile",
                "--vars",
                '{"schema":"analytics","limit":10,"enabled":true,"optional":null,'
                '"grants":{"role":"analyst"},"roles":["reporter"]}',
            ],
            expected_exit_code=3,
            expected_vars={
                "schema": "analytics",
                "limit": 10,
                "enabled": True,
                "optional": None,
                "grants": {"role": "analyst"},
                "roles": ["reporter"],
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_compile_no_sql_validation_when_running_then_dispatches_expected_flag(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            bool,
            str | None,
            bool,
            bool,
            str | None,
            bool,
            CompileLineageMode,
            dict[str, object] | None,
            bool,
            bool,
            bool,
            bool,
        ]
    ] = []

    def run_compile(request: CompileCommandRequest) -> int:
        received_args.append(
            (
                request.project_dir,
                request.no_sql_validation,
                request.defer_to,
                request.json_output,
                request.manifest,
                request.dag_path,
                request.no_color,
                request.lineage_mode,
                request.cli_vars,
                request.profile_flags.skip_discovery_sql_analysis,
                request.profile_flags.skip_column_inference,
                request.profile_flags.skip_contracts,
                request.profile_flags.skip_write,
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
            test_case.expected_dag,
            False,
            test_case.expected_compile_lineage_mode,
            {} if test_case.expected_vars is None else test_case.expected_vars,
            False,
            False,
            False,
            False,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes dag json and no sql validation flags to handler",
            argv=["dag", "--json", "--no-sql-validation"],
            expected_exit_code=3,
            expected_no_sql_validation=True,
        ),
        MainTestCase(
            description="passes sqlbuild vars to dag handler",
            argv=["dag", "--vars", '{"schema":"analytics"}'],
            expected_exit_code=3,
            expected_vars={"schema": "analytics"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dag_command_arguments_when_running_then_dispatches_expected_handler(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, bool, bool, dict[str, object]]] = []

    def run_dag(
        project_dir: Path | None,
        no_sql_validation: bool,
        json_output: bool,
        cli_vars: dict[str, object],
    ) -> int:
        received_args.append((project_dir, no_sql_validation, json_output, cli_vars))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_dag=run_dag),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (
            test_case.expected_project_dir,
            test_case.expected_no_sql_validation,
            "--json" in test_case.argv,
            {} if test_case.expected_vars is None else test_case.expected_vars,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes global debug and no color plus full refresh to build handler",
            argv=[
                "--debug",
                "--no-color",
                "build",
                "--full-refresh",
                "--allow-snapshot-full-refresh",
                "--allow-snapshot-schema-change",
            ],
            expected_exit_code=5,
            expected_full_refresh=True,
            expected_allow_snapshot_full_refresh=True,
            expected_allow_snapshot_schema_change=True,
            expected_no_color=True,
            expected_debug=True,
        ),
        MainTestCase(
            description="passes no load to build handler",
            argv=["build", "--no-load"],
            expected_exit_code=5,
            expected_load_sources=False,
        ),
        MainTestCase(
            description="passes load to build handler",
            argv=["build", "--load"],
            expected_exit_code=5,
            expected_load_sources=True,
        ),
        MainTestCase(
            description="passes reload to build handler",
            argv=["build", "--reload"],
            expected_exit_code=5,
            expected_reload=True,
        ),
        MainTestCase(
            description="passes no tests to build handler",
            argv=["build", "--no-tests"],
            expected_exit_code=5,
            expected_run_tests=False,
        ),
        MainTestCase(
            description="passes no audits to build handler",
            argv=["build", "--no-audits"],
            expected_exit_code=5,
            expected_run_audits=False,
        ),
        MainTestCase(
            description="passes no tests and no audits to build handler",
            argv=["build", "--no-tests", "--no-audits"],
            expected_exit_code=5,
            expected_run_tests=False,
            expected_run_audits=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_build_full_refresh_when_running_then_dispatches_expected_flag(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[bool, bool, bool, str | None, bool | None, bool, bool, bool, bool, bool, bool]
    ] = []

    def run_build(request: BuildCommandRequest) -> int:
        received_args.append(
            (
                request.no_color,
                request.fail_fast,
                request.full_refresh,
                request.virtual_env,
                request.load_sources,
                request.reload_sources,
                request.allow_snapshot_full_refresh,
                request.allow_snapshot_schema_change,
                request.run_tests,
                request.run_audits,
                request.debug,
            )
        )
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
            test_case.expected_virtual_env,
            test_case.expected_load_sources,
            test_case.expected_reload,
            test_case.expected_allow_snapshot_full_refresh,
            test_case.expected_allow_snapshot_schema_change,
            test_case.expected_run_tests,
            test_case.expected_run_audits,
            test_case.expected_debug,
        )
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes global no color to plan handler",
            argv=["--no-color", "plan", "--select", "orders", "--exclude", "customers"],
            expected_exit_code=4,
            expected_no_color=True,
            expected_select=("orders",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_plan_flags_when_running_then_dispatches_expected_arguments(
    test_case: MainTestCase,
) -> None:
    received_args: list[
        tuple[
            Path | None,
            bool,
            str | None,
            str | None,
            object,
            bool,
            bool,
            str | None,
            bool | None,
            bool,
            tuple[str, ...],
            tuple[str, ...],
            bool,
            dict[str, object] | None,
        ]
    ] = []

    def run_plan(request: PlanCommandRequest) -> int:
        received_args.append(
            (
                request.project_dir,
                request.no_sql_validation,
                request.defer_to,
                request.defer_sources_to,
                request.cursor_overrides,
                request.json_output,
                request.full_refresh,
                request.virtual_env,
                request.load_sources,
                request.no_color,
                request.select,
                request.exclude,
                request.verbose,
                request.cli_vars,
            )
        )
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_plan=run_plan),
    )

    assert exit_code == test_case.expected_exit_code
    assert len(received_args) == 1
    assert received_args[0][5:] == (
        False,
        False,
        None,
        None,
        test_case.expected_no_color,
        test_case.expected_select,
        ("customers",),
        False,
        {},
    )


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes no load to plan handler",
            argv=["plan", "--no-load"],
            expected_exit_code=4,
            expected_load_sources=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_plan_load_flag_when_running_then_dispatches_expected_argument(
    test_case: MainTestCase,
) -> None:
    received_load_sources: list[bool | None] = []

    def run_plan(request: PlanCommandRequest) -> int:
        received_load_sources.append(request.load_sources)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_plan=run_plan),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_load_sources == [test_case.expected_load_sources]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes selectors from select file to plan handler",
            argv=["plan", "--select", "orders", "--select-file", "selectors.txt"],
            expected_exit_code=4,
            expected_select=("orders", "customers", "payments"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_select_file_when_running_then_dispatches_file_selectors(
    test_case: MainTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "selectors.txt").write_text("customers\n\n# ignored\npayments\n", encoding="utf-8")
    received_selects: list[tuple[str, ...]] = []

    def run_plan(request: PlanCommandRequest) -> int:
        received_selects.append(request.select)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=[*test_case.argv[:4], str(tmp_path / test_case.argv[4])],
        handlers=build_handlers(run_plan=run_plan),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_selects == [test_case.expected_select]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes scenario selectors from select file to capture handler",
            argv=[
                "scenario",
                "capture",
                "--select",
                "orders",
                "--select-file",
                "scenario_selectors.txt",
            ],
            expected_exit_code=4,
            expected_scenario_selectors=("orders", "customers", "payments"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_select_file_when_running_then_dispatches_file_selectors(
    test_case: MainTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "scenario_selectors.txt").write_text(
        "customers\n\n# ignored\npayments\n", encoding="utf-8"
    )
    received_selects: list[tuple[str, ...]] = []

    def run_scenario_capture(request: ScenarioCaptureCommandRequest) -> int:
        received_selects.append(request.selectors)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=[*test_case.argv[:5], str(tmp_path / test_case.argv[5])],
        handlers=build_handlers(run_scenario_capture=run_scenario_capture),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_selects == [test_case.expected_scenario_selectors]


@pytest.mark.parametrize(
    "test_case",
    [
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
        MainTestCase(
            description="returns parser error for removed top level run command",
            argv=["run"],
            expected_exit_code=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_command_local_global_flags_when_running_main_then_it_returns_parser_error(
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code: int = main(test_case.argv)
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert "error[C900]:" in rendered_stderr
    assert rendered_stderr.endswith("\n\n")


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="colorizes parser error prefix when color is supported",
            argv=["build", "--debug"],
            expected_exit_code=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_parser_error_and_color_support_when_running_main_then_it_colorizes_error_prefix(
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sqlbuild.cli.commands.main.commands.entry.supports_color", lambda: True)

    exit_code: int = main(test_case.argv)
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert "\033[31m\033[1merror[C900]:\033[0m" in rendered_stderr
    assert rendered_stderr.endswith("\n\n")


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="leaves parser error plain when no color is requested",
            argv=["--no-color", "build", "--debug"],
            expected_exit_code=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_parser_error_and_no_color_when_running_main_then_it_renders_plain_error_prefix(
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sqlbuild.cli.commands.main.commands.entry.supports_color", lambda: True)

    exit_code: int = main(test_case.argv)
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert "error[C900]:" in rendered_stderr
    assert "\033[31m" not in rendered_stderr
    assert rendered_stderr.endswith("\n\n")


@pytest.mark.parametrize(
    "test_case",
    [
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
        MainErrorRenderingTestCase(
            description="renders load timestamp cursor override validation errors",
            argv=["load", "--start-cursor-ts", "not-a-timestamp"],
            error_type=ValueError,
            error_factory=lambda project_dir: ValueError("unused"),
            expected_stderr_fragment=(
                "error[S000]: --start-cursor-ts value 'not-a-timestamp' is not a valid ISO timestamp"
            ),
            expected_exit_code=1,
        ),
        MainErrorRenderingTestCase(
            description="renders load integer cursor override validation errors",
            argv=["load", "--start-cursor-int", "3.14"],
            error_type=ValueError,
            error_factory=lambda project_dir: ValueError("unused"),
            expected_stderr_fragment=(
                "error[S000]: --start-cursor-int value '3.14' is not a whole number"
            ),
            expected_exit_code=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_expected_cli_errors_when_running_main_then_it_renders_stderr_and_returns_one(
    test_case: MainErrorRenderingTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_compile(request: CompileCommandRequest) -> int:
        assert request.project_dir is not None
        raise test_case.error_factory(request.project_dir)

    def run_query(
        project_dir: Path | None,
        sql: str | None,
        selected_target: str | None,
        output_format: str,
        limit: int | None,
    ) -> int:
        del project_dir, sql, selected_target, output_format, limit
        raise test_case.error_factory(Path("/tmp/demo"))

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_compile=run_compile, run_query=run_query),
    )
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in rendered_stderr
    assert rendered_stderr.endswith("\n\n")


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
    ids=lambda case: case.description,
)
def test_given_expected_cli_error_and_color_support_when_running_main_then_it_colorizes_stderr(
    test_case: MainErrorRenderingTestCase,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sqlbuild.cli.commands.main.commands.entry.supports_color", lambda: True)

    def run_query(
        project_dir: Path | None,
        sql: str | None,
        selected_target: str | None,
        output_format: str,
        limit: int | None,
    ) -> int:
        del project_dir, sql, selected_target, output_format, limit
        raise test_case.error_factory(Path("/tmp/demo"))

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_query=run_query),
    )
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in rendered_stderr
