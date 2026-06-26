from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from sqlbuild.integrations.dbt.exceptions import DbtReuseUnavailableError
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.reuse import production_ref as production_ref_module
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCommandResult,
    DbtProductionRefCompileResult,
)
from sqlbuild.spec.models.project import DbtProductionRefConfig
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtReuseCompileDepsTestCase,
    DbtReuseGitRefreshTestCase,
    DbtReuseGitTimeoutTestCase,
    DbtReuseManifestCacheTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseGitTimeoutTestCase(
            description="raises reuse unavailable when git command times out",
            timeout_seconds=7,
            expected_error_fragment="timed out after 7s",
        )
    ],
    ids=["raises reuse unavailable when git command times out"],
)
def test_given_git_command_timeout_when_running_git_text_then_raises_reuse_unavailable(
    test_case: DbtReuseGitTimeoutTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=("git", "fetch"), timeout=test_case.timeout_seconds)

    monkeypatch.setattr(production_ref_module.subprocess, "run", run)

    with pytest.raises(DbtReuseUnavailableError, match=test_case.expected_error_fragment):
        production_ref_module._run_git_text("fetch", timeout_seconds=test_case.timeout_seconds)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseGitRefreshTestCase(
            description="refresh false archives configured local ref without fetching",
            git_ref="master",
            refresh=False,
            expected_archive_ref="master",
            expected_run_calls=0,
        )
    ],
    ids=["refresh false archives configured local ref without fetching"],
)
def test_given_refresh_disabled_when_refreshing_git_ref_then_skips_fetch(
    test_case: DbtReuseGitRefreshTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_calls: list[tuple[object, ...]] = []

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        run_calls.append(args)
        return subprocess.CompletedProcess(args=("git",), returncode=0, stdout="", stderr="")

    monkeypatch.setattr(production_ref_module.subprocess, "run", run)

    archive_ref: str = production_ref_module._refresh_git_ref_for_archive(
        git_root=Path("/repo"),
        git_ref=test_case.git_ref,
        refresh=test_case.refresh,
        timeout_seconds=30,
    )

    assert archive_ref == test_case.expected_archive_ref
    assert len(run_calls) == test_case.expected_run_calls


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseCompileDepsTestCase(
            description="runs dbt deps before compile when archived project declares packages",
            expected_commands=("deps", "compile"),
            expected_manifest_contents='{"metadata": {}}',
        )
    ],
    ids=["runs dbt deps before compile when archived project declares packages"],
)
def test_given_reuse_checkout_with_packages_when_compiling_then_runs_deps_before_compile(
    test_case: DbtReuseCompileDepsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlbuild_project_dir: Path = tmp_path / "sqlbuild_project"
    macro_source: Path = sqlbuild_project_dir / "dbt" / "macros" / "generate_schema_name.sql"
    macro_source.parent.mkdir(parents=True)
    macro_source.write_text(
        "{% macro generate_schema_name(custom_schema_name, node) %}{% endmacro %}", encoding="utf-8"
    )
    dbt_project_dir: Path = tmp_path / "repo" / "dbt_project"
    dbt_project_dir.mkdir(parents=True)
    command_names: list[str] = []

    def extract_git_ref(
        *, git_root: Path, git_ref: str, destination: Path, timeout_seconds: int
    ) -> None:
        del git_root, git_ref, timeout_seconds
        temp_project_dir: Path = destination / "dbt_project"
        temp_project_dir.mkdir()
        (temp_project_dir / "packages.yml").write_text("packages: []\n", encoding="utf-8")
        target_path: Path = destination.parent / "target"
        target_path.mkdir()
        (target_path / "manifest.json").write_text(
            test_case.expected_manifest_contents,
            encoding="utf-8",
        )

    def invoke(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        del cwd
        command_names.append(argv[1])
        return DbtCommandResult(argv=argv, returncode=0)

    monkeypatch.setattr(production_ref_module, "_git_root", lambda *, path: tmp_path / "repo")
    monkeypatch.setattr(production_ref_module, "_raise_if_current_branch", lambda **kwargs: None)
    monkeypatch.setattr(
        production_ref_module, "_relative_to_git_root", lambda **kwargs: Path("dbt_project")
    )
    monkeypatch.setattr(
        production_ref_module, "_refresh_git_ref_for_archive", lambda **kwargs: "master"
    )
    monkeypatch.setattr(production_ref_module, "_raise_if_missing_git_ref", lambda **kwargs: None)
    monkeypatch.setattr(production_ref_module, "_git_commit_sha", lambda **kwargs: "abc123")
    monkeypatch.setattr(production_ref_module, "_extract_git_ref", extract_git_ref)

    result: DbtProductionRefCompileResult = production_ref_module.compile_production_ref_manifest(
        sqlbuild_project_dir=sqlbuild_project_dir,
        dbt_options=DbtCliOptions(project_dir=dbt_project_dir),
        production_ref=DbtProductionRefConfig(
            git_ref="master",
            generate_schema_name_override="dbt/macros/generate_schema_name.sql",
        ),
        runner=DbtRunner(dbt_executable="dbt", invoker=invoke),
    )

    assert tuple(command_names) == test_case.expected_commands
    assert result.manifest_contents == test_case.expected_manifest_contents


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseCompileDepsTestCase(
            description="precomputes seed content hashes before reuse checkout is deleted",
            expected_commands=("compile",),
            expected_manifest_contents="",
        )
    ],
    ids=["precomputes seed content hashes before temp checkout is deleted"],
)
def test_given_reuse_manifest_with_seed_when_indexing_after_compile_then_has_no_seed_warning(
    test_case: DbtReuseCompileDepsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlbuild_project_dir: Path = tmp_path / "sqlbuild_project"
    macro_source: Path = sqlbuild_project_dir / "dbt" / "macros" / "generate_schema_name.sql"
    macro_source.parent.mkdir(parents=True)
    macro_source.write_text(
        "{% macro generate_schema_name(custom_schema_name, node) %}{% endmacro %}",
        encoding="utf-8",
    )
    dbt_project_dir: Path = tmp_path / "repo" / "dbt_project"
    dbt_project_dir.mkdir(parents=True)
    command_names: list[str] = []

    def extract_git_ref(
        *, git_root: Path, git_ref: str, destination: Path, timeout_seconds: int
    ) -> None:
        del git_root, git_ref, timeout_seconds
        temp_project_dir: Path = destination / "dbt_project"
        seed_dir: Path = temp_project_dir / "seeds"
        seed_dir.mkdir(parents=True)
        (seed_dir / "countries.csv").write_text("id,name\n1,GB\n", encoding="utf-8")
        target_path: Path = destination.parent / "target"
        target_path.mkdir()
        manifest_data: dict[str, object] = {
            "nodes": {
                "seed.analytics.countries": {
                    "unique_id": "seed.analytics.countries",
                    "resource_type": "seed",
                    "package_name": "analytics",
                    "name": "countries",
                    "checksum": {"checksum": "stale"},
                    "root_path": str(temp_project_dir),
                    "original_file_path": "seeds/countries.csv",
                }
            }
        }
        (target_path / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    def invoke(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        del cwd
        command_names.append(argv[1])
        return DbtCommandResult(argv=argv, returncode=0)

    monkeypatch.setattr(production_ref_module, "_git_root", lambda *, path: tmp_path / "repo")
    monkeypatch.setattr(production_ref_module, "_raise_if_current_branch", lambda **kwargs: None)
    monkeypatch.setattr(
        production_ref_module, "_relative_to_git_root", lambda **kwargs: Path("dbt_project")
    )
    monkeypatch.setattr(
        production_ref_module, "_refresh_git_ref_for_archive", lambda **kwargs: "master"
    )
    monkeypatch.setattr(production_ref_module, "_raise_if_missing_git_ref", lambda **kwargs: None)
    monkeypatch.setattr(production_ref_module, "_git_commit_sha", lambda **kwargs: "abc123")
    monkeypatch.setattr(production_ref_module, "_extract_git_ref", extract_git_ref)

    result: DbtProductionRefCompileResult = production_ref_module.compile_production_ref_manifest(
        sqlbuild_project_dir=sqlbuild_project_dir,
        dbt_options=DbtCliOptions(project_dir=dbt_project_dir),
        production_ref=DbtProductionRefConfig(
            git_ref="master",
            generate_schema_name_override="dbt/macros/generate_schema_name.sql",
        ),
        runner=DbtRunner(dbt_executable="dbt", invoker=invoke),
    )
    index: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(result.manifest_contents)
    )

    assert tuple(command_names) == test_case.expected_commands
    assert index.seed_identity_warnings == ()
    assert index.seeds_by_unique_id["seed.analytics.countries"].identity_hash is not None


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseManifestCacheTestCase(
            description="uses cached manifest on second compile for same reuse inputs",
            expected_first_commands=("deps", "compile"),
            expected_second_commands=(),
            expected_manifest_contents='{"metadata": {}}',
        )
    ],
    ids=["uses cached manifest on second compile for same reuse inputs"],
)
def test_given_cached_reuse_manifest_when_compiling_same_inputs_then_skips_deps_and_compile(
    test_case: DbtReuseManifestCacheTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlbuild_project_dir: Path = tmp_path / "sqlbuild_project"
    macro_source: Path = sqlbuild_project_dir / "dbt" / "macros" / "generate_schema_name.sql"
    macro_source.parent.mkdir(parents=True)
    macro_source.write_text(
        "{% macro generate_schema_name(custom_schema_name, node) %}{% endmacro %}",
        encoding="utf-8",
    )
    dbt_project_dir: Path = tmp_path / "repo" / "dbt_project"
    dbt_project_dir.mkdir(parents=True)
    command_names: list[str] = []

    def extract_git_ref(
        *, git_root: Path, git_ref: str, destination: Path, timeout_seconds: int
    ) -> None:
        del git_root, git_ref, timeout_seconds
        temp_project_dir: Path = destination / "dbt_project"
        temp_project_dir.mkdir()
        (temp_project_dir / "packages.yml").write_text("packages: []\n", encoding="utf-8")
        target_path: Path = destination.parent / "target"
        target_path.mkdir()
        (target_path / "manifest.json").write_text(
            test_case.expected_manifest_contents,
            encoding="utf-8",
        )

    def invoke(argv: tuple[str, ...], cwd: Path | None) -> DbtCommandResult:
        del cwd
        command_names.append(argv[1])
        return DbtCommandResult(argv=argv, returncode=0)

    monkeypatch.setattr(production_ref_module, "_git_root", lambda *, path: tmp_path / "repo")
    monkeypatch.setattr(production_ref_module, "_raise_if_current_branch", lambda **kwargs: None)
    monkeypatch.setattr(
        production_ref_module, "_relative_to_git_root", lambda **kwargs: Path("dbt_project")
    )
    monkeypatch.setattr(
        production_ref_module, "_refresh_git_ref_for_archive", lambda **kwargs: "master"
    )
    monkeypatch.setattr(production_ref_module, "_raise_if_missing_git_ref", lambda **kwargs: None)
    monkeypatch.setattr(production_ref_module, "_git_commit_sha", lambda **kwargs: "abc123")
    monkeypatch.setattr(production_ref_module, "_extract_git_ref", extract_git_ref)
    production_ref: DbtProductionRefConfig = DbtProductionRefConfig(
        git_ref="master",
        generate_schema_name_override="dbt/macros/generate_schema_name.sql",
    )
    dbt_options: DbtCliOptions = DbtCliOptions(project_dir=dbt_project_dir)
    runner: DbtRunner = DbtRunner(dbt_executable="dbt", invoker=invoke)

    first_result: DbtProductionRefCompileResult = (
        production_ref_module.compile_production_ref_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=dbt_options,
            production_ref=production_ref,
            runner=runner,
        )
    )
    first_commands: tuple[str, ...] = tuple(command_names)
    command_names.clear()
    second_result: DbtProductionRefCompileResult = (
        production_ref_module.compile_production_ref_manifest(
            sqlbuild_project_dir=sqlbuild_project_dir,
            dbt_options=dbt_options,
            production_ref=production_ref,
            runner=runner,
        )
    )

    assert first_commands == test_case.expected_first_commands
    assert tuple(command_names) == test_case.expected_second_commands
    assert first_result.manifest_contents == test_case.expected_manifest_contents
    assert second_result.manifest_contents == test_case.expected_manifest_contents
    assert (sqlbuild_project_dir / "target" / "sqlbuild" / "cache" / "dbt_production_ref").is_dir()
