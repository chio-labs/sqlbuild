"""E2E tests for provider command wiring."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import build_virtual_plan_project_toml
from tests.e2e.src.sqlbuild.cli.commands.main.providers._test_types import (
    ProviderCommandConcurrencyE2ETestCase,
    ProviderCommandDiagnosticE2ETestCase,
    ProviderCommandE2ETestCase,
    ProviderCommandFailureE2ETestCase,
    ProviderCommandSideEffectE2ETestCase,
    ProviderCustomMaterializationE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)

PROVIDER_FAILURE_PROJECT_TOML: str = (
    dedent(
        """
    name = "provider_failure_project"
    adapter = "duckdb"

    [connection]
    database = "provider_failure_project.duckdb"
    """
    ).strip()
    + "\n"
)

PROVIDER_MARKER_FILE: str = (
    dedent(
        """
    from pathlib import Path

    from pydantic import Field
    from sqlbuild.providers import Provider


    class MarkerProvider(Provider):
        marker_path: str = Field(validation_alias="MARKER_PATH")

        def setup(self, ctx):
            self.mark("setup")

        def teardown(self):
            self.mark("teardown")

        def mark(self, value):
            path = Path(self.marker_path)
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(existing + value + "\\n", encoding="utf-8")
    """
    ).strip()
    + "\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderCommandE2ETestCase(
            description="providers are available in run build check and load commands",
            expected_exit_code=0,
            expected_marker_entries=(
                "setup",
                "run_task:provider-e2e",
                "teardown",
                "setup",
                "build_asset:provider-e2e",
                "teardown",
                "setup",
                "check:provider-e2e",
                "teardown",
                "setup",
                "load:provider-e2e",
                "teardown",
            ),
            expected_loaded_rows=((1, "provider-e2e"),),
        )
    ],
    ids=["providers are available in run build check and load commands"],
)
def test_given_project_with_provider_when_running_commands_then_provider_is_injected(
    test_case: ProviderCommandE2ETestCase,
    tmp_path: Path,
) -> None:
    marker_path: Path = tmp_path / "provider-marker.log"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="provider_command_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "provider_command_project"
                adapter = "duckdb"

                [connection]
                database = "provider_command_project.duckdb"
                """
            ).strip()
            + "\n",
            "providers/marker.py": dedent(
                """
                from pathlib import Path

                from pydantic import Field
                from sqlbuild.providers import Provider


                class MarkerProvider(Provider):
                    marker_path: str = Field(validation_alias="MARKER_PATH")
                    label: str = "provider-e2e"

                    def setup(self, ctx):
                        self.mark("setup")

                    def teardown(self):
                        self.mark("teardown")

                    def mark(self, value):
                        path = Path(self.marker_path)
                        existing = path.read_text(encoding="utf-8") if path.exists() else ""
                        path.write_text(existing + value + "\\n", encoding="utf-8")
                """
            ).strip()
            + "\n",
            "tasks/provider_task.py": dedent(
                """
                from providers.marker import MarkerProvider
                from sqlbuild.tasks import task


                @task
                def provider_task(ctx, marker_provider: MarkerProvider):
                    marker_provider.mark(f"run_task:{marker_provider.label}")
                """
            ).strip()
            + "\n",
            "assets/provider_asset.py": dedent(
                """
                from providers.marker import MarkerProvider
                from sqlbuild.assets import asset


                @asset
                def provider_asset(ctx, marker_provider: MarkerProvider):
                    marker_provider.mark(f"build_asset:{marker_provider.label}")
                """
            ).strip()
            + "\n",
            "checks/provider_check.py": dedent(
                """
                from providers.marker import MarkerProvider
                from sqlbuild.checks import check


                @check(depends_on=())
                def provider_check(ctx, marker_provider: MarkerProvider):
                    marker_provider.mark(f"check:{marker_provider.label}")
                    return True
                """
            ).strip()
            + "\n",
            "loaders/provider_loader.py": dedent(
                """
                from providers.marker import MarkerProvider
                from sqlbuild.loaders import loader


                @loader
                def raw_provider_events(ctx, marker_provider: MarkerProvider):
                    marker_provider.mark(f"load:{marker_provider.label}")
                    return [{"event_id": 1, "label": marker_provider.label}]
                """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_provider_events
                    managed: true
                    write_strategy: table
                    columns:
                      - name: event_id
                        type: INTEGER
                      - name: label
                        type: VARCHAR
                """
            ).strip()
            + "\n",
        },
    )
    env: dict[str, str] = {"MARKER_PATH": str(marker_path)}

    run_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "run", "--select", "provider_task"),
        project_dir=project_dir,
        env=env,
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "provider_asset"),
        project_dir=project_dir,
        env=env,
    )
    check_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "check", "--select", "provider_check"),
        project_dir=project_dir,
        env=env,
    )
    load_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "load", "--select", "raw_provider_events"),
        project_dir=project_dir,
        env=env,
    )

    for result in (run_result, build_result, check_result, load_result):
        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr

    marker_entries: tuple[str, ...] = tuple(
        line for line in marker_path.read_text(encoding="utf-8").splitlines() if line
    )
    assert marker_entries == test_case.expected_marker_entries
    loaded_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "provider_command_project.duckdb",
        sql="SELECT event_id, label FROM raw_provider_events ORDER BY event_id",
    )
    assert tuple(loaded_rows) == test_case.expected_loaded_rows


PROVIDER_COMMAND_FAILURE_TEST_CASES: tuple[ProviderCommandFailureE2ETestCase, ...] = (
    ProviderCommandFailureE2ETestCase(
        description="run provider tears down when command fails after setup",
        command=("--no-color", "run", "--select", "failing_task"),
        repo_files={
            "sqlbuild_project.toml": PROVIDER_FAILURE_PROJECT_TOML,
            "providers/marker.py": PROVIDER_MARKER_FILE,
            "tasks/failing_task.py": dedent(
                """
                    from providers.marker import MarkerProvider
                    from sqlbuild.tasks import task


                    @task
                    def failing_task(ctx, marker_provider: MarkerProvider):
                        marker_provider.mark("task")
                        raise RuntimeError("intentional provider failure")
                    """
            ).strip()
            + "\n",
        },
        expected_marker_entries=("setup", "task", "teardown"),
    ),
    ProviderCommandFailureE2ETestCase(
        description="build provider tears down when command fails after setup",
        command=("--no-color", "build", "--select", "failing_asset"),
        repo_files={
            "sqlbuild_project.toml": PROVIDER_FAILURE_PROJECT_TOML,
            "providers/marker.py": PROVIDER_MARKER_FILE,
            "assets/failing_asset.py": dedent(
                """
                    from providers.marker import MarkerProvider
                    from sqlbuild.assets import asset


                    @asset
                    def failing_asset(ctx, marker_provider: MarkerProvider):
                        marker_provider.mark("asset")
                        raise RuntimeError("intentional provider failure")
                    """
            ).strip()
            + "\n",
        },
        expected_marker_entries=("setup", "asset", "teardown"),
    ),
    ProviderCommandFailureE2ETestCase(
        description="check provider tears down when command fails after setup",
        command=("--no-color", "check", "--select", "failing_check"),
        repo_files={
            "sqlbuild_project.toml": PROVIDER_FAILURE_PROJECT_TOML,
            "providers/marker.py": PROVIDER_MARKER_FILE,
            "checks/failing_check.py": dedent(
                """
                    from providers.marker import MarkerProvider
                    from sqlbuild.checks import check


                    @check(depends_on=())
                    def failing_check(ctx, marker_provider: MarkerProvider):
                        marker_provider.mark("check")
                        raise RuntimeError("intentional provider failure")
                    """
            ).strip()
            + "\n",
        },
        expected_marker_entries=("setup", "check", "teardown"),
    ),
    ProviderCommandFailureE2ETestCase(
        description="load provider tears down when command fails after setup",
        command=("--no-color", "load", "--select", "raw_provider_events"),
        repo_files={
            "sqlbuild_project.toml": PROVIDER_FAILURE_PROJECT_TOML,
            "providers/marker.py": PROVIDER_MARKER_FILE,
            "loaders/failing_loader.py": dedent(
                """
                    from providers.marker import MarkerProvider
                    from sqlbuild.loaders import loader


                    @loader
                    def raw_provider_events(ctx, marker_provider: MarkerProvider):
                        marker_provider.mark("load")
                        raise RuntimeError("intentional provider failure")
                    """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                    sources:
                      - name: raw_provider_events
                        managed: true
                        write_strategy: table
                        columns:
                          - name: event_id
                            type: INTEGER
                    """
            ).strip()
            + "\n",
        },
        expected_marker_entries=("setup", "load", "teardown"),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    PROVIDER_COMMAND_FAILURE_TEST_CASES,
    ids=[case.description for case in PROVIDER_COMMAND_FAILURE_TEST_CASES],
)
def test_given_provider_backed_command_failure_when_provider_was_setup_then_provider_tears_down(
    test_case: ProviderCommandFailureE2ETestCase,
    tmp_path: Path,
) -> None:
    marker_path: Path = tmp_path / "provider-failure-marker.log"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="provider_failure_project",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
        env={"MARKER_PATH": str(marker_path)},
    )

    assert result.returncode != 0, result.stdout + result.stderr
    marker_entries: tuple[str, ...] = tuple(marker_path.read_text(encoding="utf-8").splitlines())
    assert marker_entries == test_case.expected_marker_entries


PROVIDER_COMMAND_SIDE_EFFECT_TEST_CASES: tuple[ProviderCommandSideEffectE2ETestCase, ...] = (
    ProviderCommandSideEffectE2ETestCase(
        description="compile discovers typed providers without setup side effects",
        command=("--no-color", "compile"),
        expected_marker_exists=False,
    ),
    ProviderCommandSideEffectE2ETestCase(
        description="plan discovers typed providers without setup side effects",
        command=("--no-color", "plan"),
        expected_marker_exists=False,
    ),
)


@pytest.mark.parametrize(
    "test_case",
    PROVIDER_COMMAND_SIDE_EFFECT_TEST_CASES,
    ids=[case.description for case in PROVIDER_COMMAND_SIDE_EFFECT_TEST_CASES],
)
def test_given_provider_project_when_running_compile_or_plan_then_provider_setup_is_not_called(
    test_case: ProviderCommandSideEffectE2ETestCase,
    tmp_path: Path,
) -> None:
    marker_path: Path = tmp_path / "provider-side-effect-marker.log"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="provider_side_effect_project",
        repo_files={
            "sqlbuild_project.toml": PROVIDER_FAILURE_PROJECT_TOML,
            "providers/marker.py": PROVIDER_MARKER_FILE,
            "tasks/provider_task.py": dedent(
                """
                from providers.marker import MarkerProvider
                from sqlbuild.tasks import task


                @task
                def provider_task(ctx, marker_provider: MarkerProvider):
                    marker_provider.mark("task")
                """
            ).strip()
            + "\n",
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
        env={"MARKER_PATH": str(marker_path)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert marker_path.exists() is test_case.expected_marker_exists


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderCommandDiagnosticE2ETestCase(
            description="alias-imported provider annotation gets CLI diagnostic",
            command=("--no-color", "run", "--select", "alias_task"),
            expected_error_fragment=(
                "Import project providers using the project-root providers package path"
            ),
        )
    ],
    ids=["alias-imported provider annotation gets CLI diagnostic"],
)
def test_given_alias_imported_provider_annotation_when_running_command_then_cli_prints_guidance(
    test_case: ProviderCommandDiagnosticE2ETestCase,
    tmp_path: Path,
) -> None:
    marker_path: Path = tmp_path / "provider-alias-marker.log"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="provider_alias_project",
        repo_files={
            "sqlbuild_project.toml": PROVIDER_FAILURE_PROJECT_TOML,
            "providers/marker.py": PROVIDER_MARKER_FILE,
            "tasks/alias_task.py": dedent(
                """
                import importlib.util
                import sys
                from pathlib import Path

                from sqlbuild.tasks import task

                provider_path = Path(__file__).parents[1] / "providers" / "marker.py"
                spec = importlib.util.spec_from_file_location("alias_marker", provider_path)
                alias_marker = importlib.util.module_from_spec(spec)
                sys.modules["alias_marker"] = alias_marker
                assert spec.loader is not None
                spec.loader.exec_module(alias_marker)
                AliasMarkerProvider = alias_marker.MarkerProvider


                @task
                def alias_task(ctx, marker_provider: AliasMarkerProvider):
                    marker_provider.mark("task")
                """
            ).strip()
            + "\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
        env={"MARKER_PATH": str(marker_path)},
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert test_case.expected_error_fragment in result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderCommandFailureE2ETestCase(
            description="virtual build provider tears down when command fails after setup",
            command=("--no-color", "build", "--select", "+fact_orders"),
            repo_files={
                "sqlbuild_project.toml": build_virtual_plan_project_toml(),
                "providers/marker.py": PROVIDER_MARKER_FILE,
                "tasks/failing_task.py": dedent(
                    """
                    from sqlbuild.refs import model
                    from providers.marker import MarkerProvider
                    from sqlbuild.tasks import task


                    @task(depends_on=model("fact_orders"))
                    def failing_task(ctx, marker_provider: MarkerProvider):
                        marker_provider.mark("virtual_task")
                        raise RuntimeError("intentional provider failure")
                    """
                ).strip()
                + "\n",
                "models/fact_orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
            },
            expected_marker_entries=("setup", "virtual_task", "teardown"),
        )
    ],
    ids=["virtual build provider tears down when command fails after setup"],
)
def test_given_virtual_build_provider_failure_when_provider_was_setup_then_provider_tears_down(
    test_case: ProviderCommandFailureE2ETestCase,
    tmp_path: Path,
) -> None:
    marker_path: Path = tmp_path / "provider-virtual-marker.log"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="provider_virtual_project",
        repo_files=test_case.repo_files,
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
        env={"MARKER_PATH": str(marker_path)},
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
        env={"MARKER_PATH": str(marker_path)},
    )

    assert result.returncode != 0, result.stdout + result.stderr
    marker_entries: tuple[str, ...] = tuple(marker_path.read_text(encoding="utf-8").splitlines())
    assert marker_entries == test_case.expected_marker_entries


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderCustomMaterializationE2ETestCase(
            description="custom materialization gets providers and tears down after failure",
            command=("--no-color", "build", "--select", "orders"),
            expected_marker_entries=("setup", "ctx", "injected", "teardown"),
            expected_exit_code=1,
        )
    ],
    ids=["custom materialization gets providers and tears down after failure"],
)
def test_given_custom_materialization_with_provider_when_it_fails_then_provider_tears_down(
    test_case: ProviderCustomMaterializationE2ETestCase,
    tmp_path: Path,
) -> None:
    marker_path: Path = tmp_path / "provider-custom-marker.log"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="provider_custom_materialization_project",
        repo_files={
            "sqlbuild_project.toml": PROVIDER_FAILURE_PROJECT_TOML,
            "providers/marker.py": PROVIDER_MARKER_FILE,
            "materializations/marker_mat.py": dedent(
                """
                from providers.marker import MarkerProvider
                from sqlbuild.executor.custom.models import MaterializationContext


                def materialize(
                    ctx: MaterializationContext,
                    marker_provider: MarkerProvider,
                ):
                    ctx.providers["marker_provider"].mark("ctx")
                    marker_provider.mark("injected")
                    raise RuntimeError("intentional custom provider failure")
                """
            ).strip()
            + "\n",
            "models/orders.sql": "MODEL (materialized marker_mat);\n\nSELECT 1 AS id\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
        env={"MARKER_PATH": str(marker_path)},
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    marker_entries: tuple[str, ...] = tuple(marker_path.read_text(encoding="utf-8").splitlines())
    assert marker_entries == test_case.expected_marker_entries


@pytest.mark.parametrize(
    "test_case",
    [
        ProviderCommandConcurrencyE2ETestCase(
            description="concurrent provider-backed source loaders share command provider session",
            command=("--no-color", "build", "--concurrency", "2"),
            expected_marker_entries=("setup", "alpha", "beta", "teardown"),
            expected_exit_code=0,
        )
    ],
    ids=["concurrent provider-backed source loaders share command provider session"],
)
def test_given_concurrent_provider_backed_nodes_when_running_command_then_share_provider_session(
    test_case: ProviderCommandConcurrencyE2ETestCase,
    tmp_path: Path,
) -> None:
    marker_path: Path = tmp_path / "provider-command-concurrent-marker.log"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="provider_command_concurrent_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "provider_command_concurrent_project"
                adapter = "duckdb"

                [connection]
                database = "provider_command_concurrent_project.duckdb"
                """
            ).strip()
            + "\n",
            "providers/concurrent_marker.py": dedent(
                f"""
                from pathlib import Path
                from time import sleep

                from sqlbuild.providers import Provider


                class ConcurrentMarkerProvider(Provider):
                    marker_path: str = {str(marker_path)!r}

                    @property
                    def token(self):
                        return str(id(self))

                    def setup(self, ctx):
                        sleep(0.05)
                        self.mark("setup")

                    def teardown(self):
                        self.mark("teardown")

                    def mark(self, label):
                        with Path(self.marker_path).open("a", encoding="utf-8") as marker:
                            marker.write(f"{{label}}:{{self.token}}\\n")
                """
            ).strip()
            + "\n",
            "loaders/events.py": dedent(
                """
                from providers.concurrent_marker import ConcurrentMarkerProvider
                from sqlbuild.loaders import loader


                @loader
                def raw_alpha(ctx, concurrent_marker_provider: ConcurrentMarkerProvider):
                    concurrent_marker_provider.mark("alpha")
                    return [{"event_id": 1}]


                @loader
                def raw_beta(ctx, concurrent_marker_provider: ConcurrentMarkerProvider):
                    concurrent_marker_provider.mark("beta")
                    return [{"event_id": 2}]
                """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_alpha
                    managed: true
                    write_strategy: table
                    columns:
                      - name: event_id
                        type: INTEGER
                  - name: raw_beta
                    managed: true
                    write_strategy: table
                    columns:
                      - name: event_id
                        type: INTEGER
                """
            ).strip()
            + "\n",
            "models/fact_alpha.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_alpha")\n'
            ),
            "models/fact_beta.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_beta")\n'
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    marker_entries: tuple[str, ...] = tuple(marker_path.read_text(encoding="utf-8").splitlines())
    marker_labels: tuple[str, ...] = tuple(
        entry.split(":", maxsplit=1)[0] for entry in marker_entries
    )
    marker_tokens: set[str] = {entry.split(":", maxsplit=1)[1] for entry in marker_entries}
    assert marker_labels[0] == test_case.expected_marker_entries[0]
    assert set(marker_labels[1:3]) == set(test_case.expected_marker_entries[1:3])
    assert marker_labels[3] == test_case.expected_marker_entries[3]
    assert len(marker_entries) == len(test_case.expected_marker_entries)
    assert len(marker_tokens) == 1
