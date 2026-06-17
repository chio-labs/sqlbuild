from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError, DbtInteropRuntimeError
from sqlbuild.integrations.dbt.helpers import reuse_from
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.main.compile_reuse_from_manifest import (
    compile_reuse_from_dbt_manifest,
)
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtReuseFromCompileResult,
)
from sqlbuild.spec.models.project import DbtReuseFromConfig
from tests.integration.src.sqlbuild.integrations.dbt._test_types import (
    DbtReuseFromCompileErrorTestCase,
    DbtReuseFromCompileSetupErrorTestCase,
    RealDbtReuseFromCompileTestCase,
)
from tests.integration.src.sqlbuild.integrations.dbt.helpers import (
    build_local_reuse_from_git_project,
    run_git_command,
    set_git_identity,
)

REUSE_FROM_COMPILE_ERROR_TEST_CASES: list[DbtReuseFromCompileErrorTestCase] = [
    DbtReuseFromCompileErrorTestCase(
        description="raises when git ref cannot be archived",
        git_ref="missing-ref",
        command_returncode=0,
        command_stdout="",
        expected_error_type=DbtInteropConfigError,
        expected_error_fragment="git_ref could not be archived",
    ),
    DbtReuseFromCompileErrorTestCase(
        description="raises when injected dbt compile fails",
        git_ref="prod",
        command_returncode=2,
        command_stdout="compile exploded",
        expected_error_type=DbtInteropRuntimeError,
        expected_error_fragment="dbt reuse_from compile failed",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtReuseFromCompileTestCase(
            description="compiles dbt project at git ref with schema macro override",
            git_ref="prod",
            override_relative_path=Path("dbt/macros/prod_generate_schema_name.sql"),
            expected_unique_id="model.analytics.stg_orders",
            expected_manifest_schema="prod_dev",
            expected_manifest_sql_fragment="select 1 as order_id",
        )
    ],
    ids=["compiles dbt project at git ref with schema macro override"],
)
@pytest.mark.dbt
def test_given_dbt_reuse_from_git_ref_when_compiling_then_returns_overridden_manifest(
    test_case: RealDbtReuseFromCompileTestCase,
    tmp_path: Path,
    real_dbt_executable: str,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )

    result: DbtReuseFromCompileResult = compile_reuse_from_dbt_manifest(
        sqlbuild_project_dir=sqlbuild_project_dir,
        dbt_options=DbtCliOptions(
            project_dir=dbt_project_dir,
            profiles_dir=profiles_dir,
            target_path=dbt_project_dir / "target",
        ),
        reuse_from=DbtReuseFromConfig(
            git_ref=test_case.git_ref,
            generate_schema_name_override=macro_relative_path.as_posix(),
        ),
        runner=DbtRunner(dbt_executable=real_dbt_executable),
    )

    manifest: dict[str, object] = json.loads(result.manifest_contents)
    nodes: object = manifest["nodes"]
    assert isinstance(nodes, dict)
    node: object = nodes[test_case.expected_unique_id]
    assert isinstance(node, dict)
    assert result.git_ref == test_case.git_ref
    assert result.command.returncode == 0
    assert node["schema"] == test_case.expected_manifest_schema
    assert test_case.expected_manifest_sql_fragment in str(node["raw_code"])


@pytest.mark.parametrize(
    "test_case",
    REUSE_FROM_COMPILE_ERROR_TEST_CASES,
    ids=[case.description for case in REUSE_FROM_COMPILE_ERROR_TEST_CASES],
)
def test_given_invalid_reuse_from_compile_inputs_when_compiling_then_raises_clear_error(
    test_case: DbtReuseFromCompileErrorTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )

    def invoke(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        return DbtCommandResult(
            argv=argv,
            returncode=test_case.command_returncode,
            stdout=test_case.command_stdout,
        )

    with pytest.raises(test_case.expected_error_type) as exc_info:
        compile_reuse_from_dbt_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=DbtCliOptions(
                project_dir=dbt_project_dir,
                profiles_dir=profiles_dir,
                target_path=dbt_project_dir / "target",
            ),
            reuse_from=DbtReuseFromConfig(
                git_ref=test_case.git_ref,
                generate_schema_name_override=macro_relative_path.as_posix(),
            ),
            runner=DbtRunner(invoker=invoke),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseFromCompileSetupErrorTestCase(
            description="raises when reuse git ref is current branch",
            setup_kind="current_branch",
            expected_error_fragment="git_ref must not be the current branch",
        )
    ],
    ids=["raises when reuse git ref is current branch"],
)
def test_given_reuse_from_git_ref_is_current_branch_when_compiling_then_raises_clear_error(
    test_case: DbtReuseFromCompileSetupErrorTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )

    with pytest.raises(DbtInteropConfigError) as exc_info:
        compile_reuse_from_dbt_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=DbtCliOptions(
                project_dir=dbt_project_dir,
                profiles_dir=profiles_dir,
                target_path=dbt_project_dir / "target",
            ),
            reuse_from=DbtReuseFromConfig(
                git_ref="main",
                generate_schema_name_override=macro_relative_path.as_posix(),
            ),
            runner=DbtRunner(invoker=lambda argv, cwd: DbtCommandResult(argv=argv, returncode=0)),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseFromCompileSetupErrorTestCase(
            description="raises when git executable is missing",
            setup_kind="missing_git",
            expected_error_fragment="requires git to be installed and available on PATH",
        )
    ],
    ids=["raises when git executable is missing"],
)
def test_given_git_is_missing_when_compiling_reuse_from_then_raises_clear_error(
    test_case: DbtReuseFromCompileSetupErrorTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )

    def raise_missing_git(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        raise FileNotFoundError("git")

    monkeypatch.setattr(reuse_from.subprocess, "run", raise_missing_git)

    with pytest.raises(DbtInteropConfigError) as exc_info:
        compile_reuse_from_dbt_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=DbtCliOptions(
                project_dir=dbt_project_dir,
                profiles_dir=profiles_dir,
                target_path=dbt_project_dir / "target",
            ),
            reuse_from=DbtReuseFromConfig(
                git_ref="prod",
                generate_schema_name_override=macro_relative_path.as_posix(),
            ),
            runner=DbtRunner(invoker=lambda argv, cwd: DbtCommandResult(argv=argv, returncode=0)),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseFromCompileErrorTestCase(
            description="raises when compile succeeds without manifest",
            git_ref="prod",
            command_returncode=0,
            command_stdout="",
            expected_error_type=DbtInteropRuntimeError,
            expected_error_fragment="did not produce manifest.json",
        )
    ],
    ids=["raises when compile succeeds without manifest"],
)
def test_given_dbt_compile_without_manifest_when_compiling_reuse_from_then_raises_clear_error(
    test_case: DbtReuseFromCompileErrorTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )

    def invoke(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        return DbtCommandResult(
            argv=argv,
            returncode=test_case.command_returncode,
            stdout=test_case.command_stdout,
        )

    with pytest.raises(test_case.expected_error_type) as exc_info:
        compile_reuse_from_dbt_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=DbtCliOptions(
                project_dir=dbt_project_dir,
                profiles_dir=profiles_dir,
                target_path=dbt_project_dir / "target",
            ),
            reuse_from=DbtReuseFromConfig(
                git_ref=test_case.git_ref,
                generate_schema_name_override=macro_relative_path.as_posix(),
            ),
            runner=DbtRunner(invoker=invoke),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtReuseFromCompileTestCase(
            description="refreshes tracked git ref before compiling",
            git_ref="prod",
            override_relative_path=Path("dbt/macros/prod_generate_schema_name.sql"),
            expected_unique_id="model.analytics.stg_orders",
            expected_manifest_schema="prod_dev",
            expected_manifest_sql_fragment="select 3 as order_id",
        )
    ],
    ids=["refreshes tracked git ref before compiling"],
)
def test_given_reuse_from_git_ref_tracks_remote_when_compiling_then_fetches_latest_ref(
    test_case: RealDbtReuseFromCompileTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )
    repo_dir: Path = sqlbuild_project_dir.parent
    remote_dir: Path = tmp_path / "remote.git"
    updater_dir: Path = tmp_path / "updater"
    run_git_command(repo_dir=repo_dir, args=("clone", "--bare", str(repo_dir), str(remote_dir)))
    run_git_command(repo_dir=repo_dir, args=("remote", "add", "origin", str(remote_dir)))
    run_git_command(repo_dir=repo_dir, args=("fetch", "origin", test_case.git_ref))
    run_git_command(
        repo_dir=repo_dir,
        args=("branch", "--set-upstream-to", f"origin/{test_case.git_ref}", test_case.git_ref),
    )
    run_git_command(repo_dir=tmp_path, args=("clone", str(remote_dir), str(updater_dir)))
    run_git_command(repo_dir=updater_dir, args=("checkout", test_case.git_ref))
    set_git_identity(repo_dir=updater_dir)
    updater_dir.joinpath("dbt_project/models/stg_orders.sql").write_text(
        test_case.expected_manifest_sql_fragment,
        encoding="utf-8",
    )
    run_git_command(repo_dir=updater_dir, args=("add", "."))
    run_git_command(repo_dir=updater_dir, args=("commit", "-m", "update prod model"))
    run_git_command(repo_dir=updater_dir, args=("push", "origin", test_case.git_ref))

    def invoke(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        project_dir: Path = Path(argv[argv.index("--project-dir") + 1])
        target_path: Path = Path(argv[argv.index("--target-path") + 1])
        raw_code: str = project_dir.joinpath("models/stg_orders.sql").read_text(encoding="utf-8")
        target_path.mkdir(parents=True)
        target_path.joinpath("manifest.json").write_text(
            json.dumps(
                {
                    "nodes": {
                        test_case.expected_unique_id: {
                            "schema": test_case.expected_manifest_schema,
                            "raw_code": raw_code,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        return DbtCommandResult(argv=argv, returncode=0)

    result: DbtReuseFromCompileResult = compile_reuse_from_dbt_manifest(
        sqlbuild_project_dir=sqlbuild_project_dir,
        dbt_options=DbtCliOptions(
            project_dir=dbt_project_dir,
            profiles_dir=profiles_dir,
            target_path=dbt_project_dir / "target",
        ),
        reuse_from=DbtReuseFromConfig(
            git_ref=test_case.git_ref,
            generate_schema_name_override=macro_relative_path.as_posix(),
        ),
        runner=DbtRunner(invoker=invoke),
    )

    assert test_case.expected_manifest_sql_fragment in result.manifest_contents


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtReuseFromCompileTestCase(
            description="uses local git ref when no upstream is configured",
            git_ref="prod",
            override_relative_path=Path("dbt/macros/prod_generate_schema_name.sql"),
            expected_unique_id="model.analytics.stg_orders",
            expected_manifest_schema="prod_dev",
            expected_manifest_sql_fragment="select 1 as order_id",
        )
    ],
    ids=["uses local git ref when no upstream is configured"],
)
def test_given_reuse_from_git_ref_has_no_upstream_when_compiling_then_uses_local_ref(
    test_case: RealDbtReuseFromCompileTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )

    def invoke(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        project_dir: Path = Path(argv[argv.index("--project-dir") + 1])
        target_path: Path = Path(argv[argv.index("--target-path") + 1])
        raw_code: str = project_dir.joinpath("models/stg_orders.sql").read_text(encoding="utf-8")
        target_path.mkdir(parents=True)
        target_path.joinpath("manifest.json").write_text(
            json.dumps({"nodes": {test_case.expected_unique_id: {"raw_code": raw_code}}}),
            encoding="utf-8",
        )
        return DbtCommandResult(argv=argv, returncode=0)

    result: DbtReuseFromCompileResult = compile_reuse_from_dbt_manifest(
        sqlbuild_project_dir=sqlbuild_project_dir,
        dbt_options=DbtCliOptions(
            project_dir=dbt_project_dir,
            profiles_dir=profiles_dir,
            target_path=dbt_project_dir / "target",
        ),
        reuse_from=DbtReuseFromConfig(
            git_ref=test_case.git_ref,
            generate_schema_name_override=macro_relative_path.as_posix(),
        ),
        runner=DbtRunner(invoker=invoke),
    )

    assert test_case.expected_manifest_sql_fragment in result.manifest_contents
    assert "select 2 as order_id" not in result.manifest_contents


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtReuseFromCompileTestCase(
            description="uses local git ref when tracking config is local only",
            git_ref="prod",
            override_relative_path=Path("dbt/macros/prod_generate_schema_name.sql"),
            expected_unique_id="model.analytics.stg_orders",
            expected_manifest_schema="prod_dev",
            expected_manifest_sql_fragment="select 1 as order_id",
        )
    ],
    ids=["uses local git ref when tracking config is local only"],
)
def test_given_reuse_from_git_ref_has_local_tracking_when_compiling_then_uses_local_ref(
    test_case: RealDbtReuseFromCompileTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )
    repo_dir: Path = sqlbuild_project_dir.parent
    run_git_command(repo_dir=repo_dir, args=("config", "branch.prod.remote", "."))
    run_git_command(repo_dir=repo_dir, args=("config", "branch.prod.merge", "refs/heads/prod"))

    def invoke(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        project_dir: Path = Path(argv[argv.index("--project-dir") + 1])
        target_path: Path = Path(argv[argv.index("--target-path") + 1])
        raw_code: str = project_dir.joinpath("models/stg_orders.sql").read_text(encoding="utf-8")
        target_path.mkdir(parents=True)
        target_path.joinpath("manifest.json").write_text(
            json.dumps({"nodes": {test_case.expected_unique_id: {"raw_code": raw_code}}}),
            encoding="utf-8",
        )
        return DbtCommandResult(argv=argv, returncode=0)

    result: DbtReuseFromCompileResult = compile_reuse_from_dbt_manifest(
        sqlbuild_project_dir=sqlbuild_project_dir,
        dbt_options=DbtCliOptions(
            project_dir=dbt_project_dir,
            profiles_dir=profiles_dir,
            target_path=dbt_project_dir / "target",
        ),
        reuse_from=DbtReuseFromConfig(
            git_ref=test_case.git_ref,
            generate_schema_name_override=macro_relative_path.as_posix(),
        ),
        runner=DbtRunner(invoker=invoke),
    )

    assert test_case.expected_manifest_sql_fragment in result.manifest_contents
    assert "select 2 as order_id" not in result.manifest_contents


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseFromCompileSetupErrorTestCase(
            description="raises when tracked git ref cannot be refreshed",
            setup_kind="refresh_failure",
            expected_error_fragment="git_ref could not be refreshed from its remote",
        )
    ],
    ids=["raises when tracked git ref cannot be refreshed"],
)
def test_given_reuse_from_git_ref_refresh_fails_when_compiling_then_raises_clear_error(
    test_case: DbtReuseFromCompileSetupErrorTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )
    repo_dir: Path = sqlbuild_project_dir.parent
    run_git_command(repo_dir=repo_dir, args=("config", "branch.prod.remote", "missing-origin"))
    run_git_command(repo_dir=repo_dir, args=("config", "branch.prod.merge", "refs/heads/prod"))

    with pytest.raises(DbtInteropConfigError) as exc_info:
        compile_reuse_from_dbt_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=DbtCliOptions(
                project_dir=dbt_project_dir,
                profiles_dir=profiles_dir,
                target_path=dbt_project_dir / "target",
            ),
            reuse_from=DbtReuseFromConfig(
                git_ref="prod",
                generate_schema_name_override=macro_relative_path.as_posix(),
            ),
            runner=DbtRunner(invoker=lambda argv, cwd: DbtCommandResult(argv=argv, returncode=0)),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseFromCompileSetupErrorTestCase(
            description="raises when dbt project directory is missing",
            setup_kind="missing_project_dir",
            expected_error_fragment="dbt project directory is not configured",
        )
    ],
    ids=["raises when dbt project directory is missing"],
)
def test_given_missing_dbt_project_dir_when_compiling_reuse_from_then_raises_clear_error(
    test_case: DbtReuseFromCompileSetupErrorTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )

    with pytest.raises(DbtInteropConfigError) as exc_info:
        compile_reuse_from_dbt_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=DbtCliOptions(
                project_dir=None,
                profiles_dir=profiles_dir,
                target_path=dbt_project_dir / "target",
            ),
            reuse_from=DbtReuseFromConfig(
                git_ref="prod",
                generate_schema_name_override=macro_relative_path.as_posix(),
            ),
            runner=DbtRunner(invoker=lambda argv, cwd: DbtCommandResult(argv=argv, returncode=0)),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseFromCompileSetupErrorTestCase(
            description="raises when macro override file is missing",
            setup_kind="missing_macro_file",
            expected_error_fragment="generate_schema_name_override was not found",
        )
    ],
    ids=["raises when macro override file is missing"],
)
def test_given_missing_macro_override_when_compiling_reuse_from_then_raises_clear_error(
    test_case: DbtReuseFromCompileSetupErrorTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )
    sqlbuild_project_dir.joinpath(macro_relative_path).unlink()

    with pytest.raises(DbtInteropConfigError) as exc_info:
        compile_reuse_from_dbt_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=DbtCliOptions(
                project_dir=dbt_project_dir,
                profiles_dir=profiles_dir,
                target_path=dbt_project_dir / "target",
            ),
            reuse_from=DbtReuseFromConfig(
                git_ref="prod",
                generate_schema_name_override=macro_relative_path.as_posix(),
            ),
            runner=DbtRunner(invoker=lambda argv, cwd: DbtCommandResult(argv=argv, returncode=0)),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseFromCompileSetupErrorTestCase(
            description="raises when SQLBuild project is not in a git repo",
            setup_kind="no_git_repo",
            expected_error_fragment="requires the SQLBuild project to be in a git repository",
        )
    ],
    ids=["raises when SQLBuild project is not in a git repo"],
)
def test_given_sqlbuild_project_outside_git_repo_when_compiling_reuse_from_then_raises_clear_error(
    test_case: DbtReuseFromCompileSetupErrorTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir: Path = tmp_path / "sqlbuild_project"
    dbt_project_dir: Path = tmp_path / "dbt_project"
    profiles_dir: Path = tmp_path / "profiles"
    macro_relative_path: Path = Path("dbt/macros/prod_generate_schema_name.sql")
    sqlbuild_project_dir.joinpath(macro_relative_path).parent.mkdir(parents=True)
    dbt_project_dir.mkdir()
    profiles_dir.mkdir()
    sqlbuild_project_dir.joinpath(macro_relative_path).write_text("macro", encoding="utf-8")

    with pytest.raises(DbtInteropConfigError) as exc_info:
        compile_reuse_from_dbt_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=DbtCliOptions(
                project_dir=dbt_project_dir,
                profiles_dir=profiles_dir,
                target_path=dbt_project_dir / "target",
            ),
            reuse_from=DbtReuseFromConfig(
                git_ref="prod",
                generate_schema_name_override=macro_relative_path.as_posix(),
            ),
            runner=DbtRunner(invoker=lambda argv, cwd: DbtCommandResult(argv=argv, returncode=0)),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseFromCompileSetupErrorTestCase(
            description="raises when dbt project is outside git repo",
            setup_kind="dbt_outside_git_repo",
            expected_error_fragment=(
                "requires the dbt project directory to be inside the git repository"
            ),
        )
    ],
    ids=["raises when dbt project is outside git repo"],
)
def test_given_dbt_project_outside_git_repo_when_compiling_reuse_from_then_raises_clear_error(
    test_case: DbtReuseFromCompileSetupErrorTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, _dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )
    dbt_project_dir: Path = tmp_path / "external_dbt_project"
    dbt_project_dir.mkdir()

    with pytest.raises(DbtInteropConfigError) as exc_info:
        compile_reuse_from_dbt_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=DbtCliOptions(
                project_dir=dbt_project_dir,
                profiles_dir=profiles_dir,
                target_path=dbt_project_dir / "target",
            ),
            reuse_from=DbtReuseFromConfig(
                git_ref="prod",
                generate_schema_name_override=macro_relative_path.as_posix(),
            ),
            runner=DbtRunner(invoker=lambda argv, cwd: DbtCommandResult(argv=argv, returncode=0)),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtReuseFromCompileTestCase(
            description="writes manifest to isolated temp target path",
            git_ref="prod",
            override_relative_path=Path("dbt/macros/prod_generate_schema_name.sql"),
            expected_unique_id="model.analytics.stg_orders",
            expected_manifest_schema="prod_dev",
            expected_manifest_sql_fragment="select 1 as order_id",
        )
    ],
    ids=["writes manifest to isolated temp target path"],
)
def test_given_reuse_from_compile_when_running_dbt_then_uses_isolated_target_path(
    test_case: RealDbtReuseFromCompileTestCase,
    tmp_path: Path,
) -> None:
    sqlbuild_project_dir, dbt_project_dir, profiles_dir, macro_relative_path = (
        build_local_reuse_from_git_project(tmp_path=tmp_path)
    )
    observed_target_paths: list[Path] = []

    def invoke(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        target_path: Path = Path(argv[argv.index("--target-path") + 1])
        observed_target_paths.append(target_path)
        target_path.mkdir(parents=True)
        target_path.joinpath("manifest.json").write_text(
            json.dumps({"nodes": {test_case.expected_unique_id: {"schema": "prod_dev"}}}),
            encoding="utf-8",
        )
        return DbtCommandResult(argv=argv, returncode=0)

    result: DbtReuseFromCompileResult = compile_reuse_from_dbt_manifest(
        sqlbuild_project_dir=sqlbuild_project_dir,
        dbt_options=DbtCliOptions(
            project_dir=dbt_project_dir,
            profiles_dir=profiles_dir,
            target_path=dbt_project_dir / "target",
        ),
        reuse_from=DbtReuseFromConfig(
            git_ref=test_case.git_ref,
            generate_schema_name_override=macro_relative_path.as_posix(),
        ),
        runner=DbtRunner(invoker=invoke),
    )

    assert observed_target_paths
    assert not observed_target_paths[0].is_relative_to(dbt_project_dir)
    assert not dbt_project_dir.joinpath("target/manifest.json").exists()
    assert test_case.expected_unique_id in result.manifest_contents
