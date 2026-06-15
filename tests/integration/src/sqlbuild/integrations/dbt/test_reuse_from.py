from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError, DbtInteropRuntimeError
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
