"""Helpers for sqb check e2e tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.main.check._test_types import CheckCommandTestCase
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_inline_project, run_sqb


def prepare_python_check_project(*, tmp_path: Path) -> Path:
    """Create an inline project with task, asset, and loader-backed Python checks."""

    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_check_project",
        repo_files={
            "sqlbuild_project.toml": """
name = "python_check_project"
adapter = "duckdb"

[connection]
database = "python_check_project.duckdb"
""",
            "tasks/orders.py": """
from sqlbuild.tasks import task


@task()
def export_orders(ctx):
    return ctx.result(payload={"rows": 3}, metadata={"rows": 3})


@task()
def export_customers(ctx):
    return ctx.result(payload={"rows": 2}, metadata={"rows": 2})
""",
            "assets/orders.py": """
from sqlbuild.assets import asset
from tasks.orders import export_orders


@asset(depends_on=export_orders)
def orders_asset(ctx):
    return ctx.result(payload={"asset_rows": 3}, metadata={"asset_rows": 3})
""",
            "checks/orders.py": """
from sqlbuild.checks import check
from assets.orders import orders_asset
from tasks.orders import export_customers, export_orders


@check(depends_on=export_orders)
def check_orders_export(ctx):
    return ctx.pass_("orders exported")


@check(depends_on=export_orders, severity="warn")
def warn_orders_export(ctx):
    return ctx.fail("warning check failed")


@check(depends_on=orders_asset, tags=("asset",), group="python-checks")
def check_orders_asset(ctx):
    return ctx.payload(orders_asset)["asset_rows"] == 3


@check(depends_on=(export_orders, export_customers), tags=("multi",), group="python-checks")
def check_order_customer_exports(ctx):
    return ctx.pass_(metadata={"orders": ctx.metadata(export_orders)["rows"]})


@check(depends_on=[export_orders], severity="error", tags=("failure",), group="python-checks")
def fail_orders_export(ctx):
    return ctx.fail("orders export failed")


@check(depends_on=export_orders, severity="error", tags=("failure",), group="python-checks")
def false_orders_export(ctx):
    return False


@check(depends_on=export_orders, severity="error", tags=("failure",), group="python-checks")
def exception_orders_export(ctx):
    raise RuntimeError("orders exception check failed")
""",
        },
    )


def prepare_terminal_loader_check_project(*, tmp_path: Path) -> Path:
    """Create a project whose check invalidly depends on a terminal source loader."""

    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="terminal_loader_check_project",
        repo_files={
            "sqlbuild_project.toml": """
name = "terminal_loader_check_project"
adapter = "duckdb"

[connection]
database = "terminal_loader_check_project.duckdb"
""",
            "loaders/raw.py": """
from sqlbuild.loaders import loader


@loader
def raw_orders(ctx):
    return [{"order_id": 1}]
""",
            "sources/raw.yml": """
sources:
  - name: raw_orders
    managed: true
    write_strategy: table
    columns:
      - name: order_id
        type: INTEGER
""",
            "checks/raw.py": """
from sqlbuild.checks import check
from loaders.raw import raw_orders


@check(depends_on=raw_orders)
def check_raw_orders_loader(ctx):
    return True
""",
        },
    )


def prepare_virtual_python_check_project(*, tmp_path: Path) -> Path:
    """Create a virtual-mode project with a task-backed Python check."""

    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_python_check_project",
        repo_files={
            "sqlbuild_project.toml": """
name = "virtual_python_check_project"
adapter = "duckdb"
[settings]
virtual_environments = true
default_target = "dev"

[connection]
database = "warehouse.duckdb"

[targets.dev]
schema = "dev"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""",
            "models/stg_orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
            "tasks/export.py": """
from sqlbuild.refs import model
from sqlbuild.tasks import task


@task(depends_on=model("stg_orders"))
def export_virtual_orders(ctx):
    return ctx.result(metadata={"rows": 1})
""",
            "checks/export.py": """
from sqlbuild.checks import check
from tasks.export import export_virtual_orders


@check(depends_on=export_virtual_orders)
def check_virtual_orders(ctx):
    return ctx.pass_("virtual orders exported")
""",
        },
    )


def prepare_virtual_failing_python_check_project(*, tmp_path: Path) -> Path:
    """Create a virtual-mode project with an error-severity Python check."""

    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_failing_python_check_project",
        repo_files={
            "sqlbuild_project.toml": """
name = "virtual_failing_python_check_project"
adapter = "duckdb"
[settings]
virtual_environments = true
default_target = "dev"

[connection]
database = "warehouse.duckdb"

[targets.dev]
schema = "dev"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""",
            "models/stg_orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
            "tasks/export.py": """
from sqlbuild.refs import model
from sqlbuild.tasks import task


@task(depends_on=model("stg_orders"))
def export_virtual_orders(ctx):
    return ctx.result(metadata={"rows": 1})
""",
            "checks/export.py": """
from sqlbuild.checks import check
from tasks.export import export_virtual_orders


@check(depends_on=export_virtual_orders)
def fail_virtual_orders(ctx):
    return ctx.fail("virtual orders failed")
""",
        },
    )


def prepare_check_project_by_kind(*, tmp_path: Path, project_kind: str) -> Path:
    """Create the project fixture for a check command test case."""

    if project_kind == "terminal_loader":
        return prepare_terminal_loader_check_project(tmp_path=tmp_path)
    if project_kind == "virtual":
        return prepare_virtual_python_check_project(tmp_path=tmp_path)
    if project_kind == "virtual_failure":
        return prepare_virtual_failing_python_check_project(tmp_path=tmp_path)
    return prepare_python_check_project(tmp_path=tmp_path)


def initialize_state_when_requested(*, project_dir: Path, test_case: CheckCommandTestCase) -> None:
    """Initialize virtual state for test cases that need it."""

    if not test_case.initialize_state:
        return
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr


def resolve_check_command(*, project_dir: Path, command: tuple[str, ...]) -> tuple[str, ...]:
    """Resolve project-dir placeholders in command arguments."""

    return tuple(part.replace("{project_dir}", str(project_dir)) for part in command)


def assert_expected_file_fragments(*, project_dir: Path, test_case: CheckCommandTestCase) -> None:
    """Assert requested project-local files exist and contain fragments."""

    relative_path: str
    fragments: tuple[str, ...]
    for relative_path, fragments in test_case.expected_file_fragments:
        file_path: Path = project_dir / relative_path
        assert file_path.exists(), f"expected file to exist: {file_path}"
        contents: str = file_path.read_text(encoding="utf-8")
        fragment: str
        for fragment in fragments:
            assert fragment in contents
