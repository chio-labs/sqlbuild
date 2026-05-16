from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.helpers.playground.copy import create_playground_project
from sqlbuild.cli.commands.main.playground import run_playground
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from tests.unit.src.sqlbuild.cli.commands.main.playground._test_types import (
    CreatePlaygroundProjectTestCase,
    RunPlaygroundTestCase,
)

CREATE_PLAYGROUND_PROJECT_TEST_CASES: list[CreatePlaygroundProjectTestCase] = [
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
            Path("functions/sql/is_completed_order.sql"),
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
            Path("dagster/definitions.py"),
            Path("dagster/README.md"),
        ),
        unexpected_paths=(Path("target"),),
    ),
]

RUN_PLAYGROUND_TEST_CASES: list[RunPlaygroundTestCase] = [
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
]


@pytest.mark.parametrize(
    "test_case",
    CREATE_PLAYGROUND_PROJECT_TEST_CASES,
    ids=[case.description for case in CREATE_PLAYGROUND_PROJECT_TEST_CASES],
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
    ids=["raises when playground target already exists"],
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
    RUN_PLAYGROUND_TEST_CASES,
    ids=[case.description for case in RUN_PLAYGROUND_TEST_CASES],
)
def test_given_playground_command_when_running_then_it_prints_next_steps(
    test_case: RunPlaygroundTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code: int = run_playground(tmp_path, test_case.target_path, template=test_case.template)

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in captured.out
    assert (tmp_path / test_case.target_path / "sqlbuild_project.toml").is_file()
    assert (tmp_path / test_case.target_path / ".agents/skills/sqlbuild/SKILL.md").is_file()
