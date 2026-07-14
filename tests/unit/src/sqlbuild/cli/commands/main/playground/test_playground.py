from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands._helpers.playground import (
    completion_output as playground_completion_output,
)
from sqlbuild.cli.commands._helpers.playground.copy import create_playground_project
from sqlbuild.cli.commands._helpers.playground.models import PlaygroundCommandRequest
from sqlbuild.cli.commands.main.commands.playground import run_playground
from sqlbuild.cli.exceptions import CliUserError
from tests.unit.src.sqlbuild.cli.commands.main.playground._test_types import (
    CreatePlaygroundProjectTestCase,
    RunPlaygroundTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CreatePlaygroundProjectTestCase(
            description="creates clean waffle shop playground from packaged template",
            target_relative_path=Path("waffle_shop_playground"),
            expected_files=(
                Path("README.md"),
                Path("sqlbuild_project.toml"),
                Path("models/staging/stg_orders.sql"),
                Path("models/marts/fact_orders.sql"),
                Path("seeds/waffle_types.csv"),
                Path("sources/raw.yml"),
                Path("tests/unit/test_daily_revenue_chain.sql"),
                Path("audits/generic/expression_is_true.sql"),
                Path("functions/sql/udf__is_completed_order.sql"),
                Path("functions/sql/table_fn__customer_orders.sql"),
                Path("loaders/waffle_sources.py"),
                Path("macros/currency.py"),
                Path("materializations/partition_tracked.py"),
            ),
            unexpected_paths=(
                Path("target"),
                Path("sqlbuild_local.toml"),
                Path("waffle_shop_control.duckdb"),
                Path("macros/__pycache__"),
            ),
        ),
        CreatePlaygroundProjectTestCase(
            description="creates Dagster playground from waffle shop template",
            target_relative_path=Path("dagster_playground"),
            template="dagster",
            expected_files=(
                Path("README.md"),
                Path("sqlbuild_project.toml"),
                Path("models/marts/fact_orders.sql"),
                Path("sources/raw.yml"),
                Path("loaders/waffle_sources.py"),
                Path("dagster/definitions.py"),
                Path("dagster/README.md"),
            ),
            unexpected_paths=(Path("target"),),
            expected_file_fragments=(
                (Path("sqlbuild_project.toml"), ('defer_sources_to = "dev"',)),
                (
                    Path("sources/raw.yml"),
                    ("managed: true",),
                ),
                (
                    Path("loaders/waffle_sources.py"),
                    ("def raw__customers(ctx", "def raw__orders(ctx"),
                ),
            ),
        ),
        CreatePlaygroundProjectTestCase(
            description="creates Rivers playground from waffle shop template",
            target_relative_path=Path("rivers_playground"),
            template="rivers",
            expected_files=(
                Path("README.md"),
                Path("sqlbuild_project.toml"),
                Path("models/marts/fact_orders.sql"),
                Path("sources/raw.yml"),
                Path("loaders/waffle_sources.py"),
                Path("rivers_pipeline/__init__.py"),
                Path("rivers_pipeline/definitions.py"),
                Path("rivers_pipeline/README.md"),
            ),
            unexpected_paths=(Path("target"),),
            expected_file_fragments=(
                (
                    Path("rivers_pipeline/definitions.py"),
                    (
                        "import rivers as rs",
                        "from sqlbuild.integrations.rivers import",
                        "@sqlbuild_assets(project=SQLBUILD_PROJECT)",
                        "repo = rs.CodeRepository",
                        'rs.Job(\n            name="waffle_shop"',
                    ),
                ),
                (
                    Path("rivers_pipeline/README.md"),
                    ("rivers dev rivers_pipeline.definitions", "`waffle_shop` job"),
                ),
            ),
        ),
        CreatePlaygroundProjectTestCase(
            description="creates loader-focused waffle shop playground from packaged template",
            target_relative_path=Path("loader_waffle_shop_playground"),
            template="loader_waffle_shop",
            expected_files=(
                Path("README.md"),
                Path("sqlbuild_project.toml"),
                Path("models/fact_waffle_orders.sql"),
                Path("models/customer_revenue.sql"),
                Path("sources/raw.yml"),
                Path("loaders/waffle_loaders.py"),
            ),
            unexpected_paths=(Path("target"), Path("sqlbuild_local.toml")),
            expected_file_fragments=(
                (Path("sources/raw.yml"), ("managed: true",)),
                (
                    Path("loaders/waffle_loaders.py"),
                    ("def raw_orders(ctx):", "def raw_customers(ctx):"),
                ),
            ),
            unexpected_file_fragments=(
                (Path("sources/raw.yml"), ("loader:",)),
                (
                    Path("loaders/waffle_loaders.py"),
                    ("def load_raw_orders(ctx):", "def load_raw_customers(ctx):"),
                ),
            ),
        ),
        CreatePlaygroundProjectTestCase(
            description="creates virtual environments playground from loader template",
            target_relative_path=Path("virtual_playground"),
            template="virtual",
            expected_files=(
                Path("README.md"),
                Path("sqlbuild_project.toml"),
                Path("models/fact_waffle_orders.sql"),
                Path("models/customer_revenue.sql"),
                Path("seeds/lookups.yml"),
                Path("seeds/waffle_price_tiers.csv"),
                Path("sources/raw.yml"),
                Path("loaders/waffle_loaders.py"),
                Path("tests/unit/test_fact_waffle_orders.sql"),
                Path("tests/scenarios/customer_revenue_minimal.sql"),
            ),
            unexpected_paths=(Path("target"), Path("sqlbuild_local.toml")),
            expected_file_fragments=(
                (
                    Path("sqlbuild_project.toml"),
                    (
                        "[settings]",
                        "virtual_environments = true",
                        "[targets.dev.state]",
                        'backend = "duckdb"',
                        'unsuffixed_virtual_env = "dev"',
                        'database = "loader_waffle_shop_state.duckdb"',
                    ),
                ),
                (
                    Path("models/fact_waffle_orders.sql"),
                    (
                        '__seed("waffle_price_tiers")',
                        "waffle_category",
                    ),
                ),
                (
                    Path("README.md"),
                    (
                        "sqb state init",
                        "sqb build --virtual-env pr",
                        "sqb scenario test",
                        "sqb diff dev:pr --schema-only",
                        "sqb promote --from pr --to dev",
                    ),
                ),
                (
                    Path("tests/unit/test_fact_waffle_orders.sql"),
                    ("__expected__fact_waffle_orders", "__seed__waffle_price_tiers"),
                ),
                (
                    Path("tests/scenarios/customer_revenue_minimal.sql"),
                    ("SCENARIO", "__expected__customer_revenue"),
                ),
            ),
        ),
        CreatePlaygroundProjectTestCase(
            description="creates Python nodes playground from generated template",
            target_relative_path=Path("python_nodes_playground"),
            template="python_nodes",
            expected_files=(
                Path("README.md"),
                Path("sqlbuild_project.toml"),
                Path("sources/raw.yml"),
                Path("models/fact_orders.sql"),
                Path("tasks/orders.py"),
                Path("loaders/orders.py"),
                Path("assets/orders_export.py"),
                Path("checks/orders_export.py"),
            ),
            unexpected_paths=(Path("target"), Path("sqlbuild_local.toml")),
            expected_file_fragments=(
                (
                    Path("tasks/orders.py"),
                    ("def prepare_raw_orders", "SkipMode.SOFT", "def export_window"),
                ),
                (
                    Path("loaders/orders.py"),
                    ("@loader(depends_on=(prepare_raw_orders,))", "def raw_orders"),
                ),
                (
                    Path("assets/orders_export.py"),
                    (
                        'ctx.relation(model("fact_orders"))',
                        "materialized=False",
                        "optional_partner_feed",
                    ),
                ),
                (
                    Path("checks/orders_export.py"),
                    ("@check(depends_on=orders_export", "ctx.result_of(orders_export)"),
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_target_when_creating_playground_then_it_copies_clean_template(
    test_case: CreatePlaygroundProjectTestCase,
    tmp_path: Path,
) -> None:
    target_dir: Path = tmp_path / test_case.target_relative_path

    create_playground_project(target_dir=target_dir, template=test_case.template)

    expected_file: Path
    for expected_file in test_case.expected_files:
        assert (target_dir / expected_file).is_file()
    unexpected_path: Path
    for unexpected_path in test_case.unexpected_paths:
        assert not (target_dir / unexpected_path).exists()
    expected_file: Path
    expected_fragments: tuple[str, ...]
    for expected_file, expected_fragments in test_case.expected_file_fragments:
        file_text: str = (target_dir / expected_file).read_text(encoding="utf-8")
        expected_fragment: str
        for expected_fragment in expected_fragments:
            assert expected_fragment in file_text
    unexpected_file: Path
    unexpected_fragments: tuple[str, ...]
    for unexpected_file, unexpected_fragments in test_case.unexpected_file_fragments:
        file_text = (target_dir / unexpected_file).read_text(encoding="utf-8")
        unexpected_fragment: str
        for unexpected_fragment in unexpected_fragments:
            assert unexpected_fragment not in file_text


@pytest.mark.parametrize(
    "test_case",
    [
        CreatePlaygroundProjectTestCase(
            description="raises when playground target already exists",
            target_relative_path=Path("existing"),
            expected_files=(),
            unexpected_paths=(),
            expected_error_fragment="playground target already exists",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_target_when_creating_playground_then_it_raises_user_error(
    test_case: CreatePlaygroundProjectTestCase,
    tmp_path: Path,
) -> None:
    target_dir: Path = tmp_path / test_case.target_relative_path
    target_dir.mkdir()

    with pytest.raises(CliUserError) as exc_info:
        create_playground_project(target_dir=target_dir)

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        RunPlaygroundTestCase(
            description="prints next steps after creating playground",
            target_path="demo_shop",
            expected_stdout_fragments=(
                "SQLBuild playground created",
                "Project: demo_shop",
                "Adapter: DuckDB",
                "sqb compile",
                "sqb build",
            ),
        ),
        RunPlaygroundTestCase(
            description="prints Dagster next steps after creating Dagster playground",
            target_path="demo_dagster_shop",
            template="dagster",
            expected_stdout_fragments=(
                "SQLBuild playground created",
                "Project: demo_dagster_shop",
                "Example: waffle shop + Dagster",
                "dagster dev -f dagster/definitions.py",
            ),
        ),
        RunPlaygroundTestCase(
            description="prints Rivers next steps after creating Rivers playground",
            target_path="demo_rivers_shop",
            template="rivers",
            expected_stdout_fragments=(
                "SQLBuild playground created",
                "Project: demo_rivers_shop",
                "Example: waffle shop + Rivers",
                "rivers dev rivers_pipeline.definitions",
            ),
        ),
        RunPlaygroundTestCase(
            description="prints loader-focused waffle shop next steps",
            target_path="demo_loader_shop",
            template="loader_waffle_shop",
            expected_stdout_fragments=(
                "SQLBuild playground created",
                "Project: demo_loader_shop",
                "Example: loader-focused waffle shop",
                "sqb build",
            ),
        ),
        RunPlaygroundTestCase(
            description="prints virtual environments next steps",
            target_path="demo_virtual_shop",
            template="virtual",
            expected_stdout_fragments=(
                "SQLBuild playground created",
                "Project: demo_virtual_shop",
                "Example: virtual environments waffle shop",
                "sqb state init",
                "sqb build --virtual-env pr",
                "sqb test",
                "sqb audit",
                "sqb scenario test",
                "sqb diff dev:pr --schema-only",
                "sqb promote --from pr --to dev",
            ),
        ),
        RunPlaygroundTestCase(
            description="prints Python nodes next steps",
            target_path="demo_python_nodes",
            template="python_nodes",
            expected_stdout_fragments=(
                "SQLBuild playground created",
                "Project: demo_python_nodes",
                "Example: Python nodes demo",
                "sqb plan --select +fact_orders --select +orders_export",
                "sqb build --select +fact_orders --select +orders_export",
                "sqb check --select check_orders_export",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_playground_command_when_running_then_it_prints_next_steps(
    test_case: RunPlaygroundTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code: int = run_playground(
        PlaygroundCommandRequest(
            project_dir=tmp_path,
            target_path=test_case.target_path,
            template=test_case.template,
        )
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in captured.out
    assert (tmp_path / test_case.target_path / "sqlbuild_project.toml").is_file()
    assert (tmp_path / test_case.target_path / ".agents/skills/sqlbuild/SKILL.md").is_file()


@pytest.mark.parametrize(
    "test_case",
    [
        RunPlaygroundTestCase(
            description="styles key playground next step elements",
            target_path="demo_color_shop",
            expected_stdout_fragments=(),
            expected_color_fragments=(
                "\033[32m\033[1mSQLBuild playground created\033[0m",
                "  \033[34m\033[1mProject\033[0m: demo_color_shop",
                "\033[32m\033[1mTry\033[0m:",
                "\033[2m  \033[0msqb compile",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_color_terminal_when_running_playground_command_then_it_styles_key_elements(
    test_case: RunPlaygroundTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(playground_completion_output, "supports_color", lambda: True)

    exit_code: int = run_playground(
        PlaygroundCommandRequest(
            project_dir=tmp_path,
            target_path=test_case.target_path,
            template=test_case.template,
        )
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    expected_fragment: str
    for expected_fragment in test_case.expected_color_fragments:
        assert expected_fragment in captured.out
