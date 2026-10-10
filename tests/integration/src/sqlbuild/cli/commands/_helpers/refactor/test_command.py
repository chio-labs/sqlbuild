"""Progress messages of `sqb rename` and `sqb mv` against a real offline compile."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.refactor.command import run_refactor_command
from sqlbuild.cli.commands.models import RefactorCommandRequest
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.integration.src.sqlbuild.cli.commands._helpers.refactor._test_types import (
    BareTargetRefactorTestCase,
    NativeEditCountTestCase,
    RefactorStatusMessagesTestCase,
)
from tests.integration.src.sqlbuild.cli.commands._helpers.refactor.helpers import (
    refactoring_answers,
    start_recording,
)

_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders_project"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
        '[connection]\ndatabase = "orders.duckdb"\n\n'
        '[targets.dev]\nschema = "analytics"\n'
    ),
    "seeds/orders.csv": "order_id,amount\n1,25\n2,40\n",
    "seeds/orders.yml": (
        "seeds:\n"
        "  - name: orders\n    description: Test seed orders.\n"
        "    columns:\n"
        "      - name: order_id\n        type: INTEGER\n"
        "      - name: amount\n        type: INTEGER\n"
    ),
    "models/staging/stg_orders.sql": (
        "MODEL (description 'Test model.',\n  materialized view,\n);\n\n"
        'SELECT\n  order_id,\n  amount\nFROM __seed("orders")\n'
    ),
    "models/marts/fact_orders.sql": (
        "MODEL (description 'Test model.',\n  materialized table,\n);\n\n"
        'SELECT\n  order_id,\n  amount\nFROM __ref("stg_orders")\n'
    ),
}


@pytest.mark.parametrize(
    "test_case",
    [
        RefactorStatusMessagesTestCase(
            description="moving a model nothing else names edits one file",
            command=CliCommand.MV,
            target="model:fact_orders",
            new_name=None,
            destination="models/finance/fact_orders.sql",
            expected_lines=(
                "Planned edits to 1 file.",
                "Writing 1 file...",
                "Wrote 1 file.",
                "Compiled: ok, 1 file changed",
            ),
        ),
        RefactorStatusMessagesTestCase(
            description="renaming a column nothing downstream reads edits one file",
            command=CliCommand.RENAME,
            target="column:fact_orders.amount",
            new_name="order_amount",
            destination=None,
            expected_lines=(
                "Planned edits to 1 file.",
                "Writing 1 file...",
                "Wrote 1 file.",
                "Compiled: ok, 1 file changed",
            ),
        ),
        RefactorStatusMessagesTestCase(
            description="renaming a model another model reads edits two files",
            command=CliCommand.RENAME,
            target="model:stg_orders",
            new_name="stg_order_lines",
            destination=None,
            expected_lines=(
                "Planned edits to 2 files.",
                "Writing 2 files...",
                "Wrote 2 files.",
                "Compiled: ok, 2 files changed",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_refactor_when_running_then_progress_messages_agree_in_number(
    test_case: RefactorStatusMessagesTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative_path: str
    content: str
    for relative_path, content in _PROJECT_FILES.items():
        path: Path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    exit_code: int = run_refactor_command(
        request=RefactorCommandRequest(
            command=test_case.command,
            target=test_case.target,
            new_name=test_case.new_name,
            destination=test_case.destination,
            project_dir=tmp_path,
            no_color=True,
        )
    )

    lines: list[str] = capsys.readouterr().out.splitlines()
    assert exit_code == 0, lines
    expected: str
    for expected in test_case.expected_lines:
        assert expected in lines, lines


@pytest.mark.parametrize(
    "test_case",
    [
        BareTargetRefactorTestCase(
            description="bare model.column renames the column downstream",
            command=CliCommand.RENAME,
            target="stg_orders.amount",
            new_name="revenue",
            destination=None,
            expected_path="models/marts/fact_orders.sql",
            expected_fragment="revenue AS amount",
            expected_missing_paths=(),
        ),
        BareTargetRefactorTestCase(
            description="bare model name moves the model file",
            command=CliCommand.MV,
            target="fact_orders",
            new_name=None,
            destination="models/finance/",
            expected_path="models/finance/fact_orders.sql",
            expected_fragment='FROM __ref("stg_orders")',
            expected_missing_paths=("models/marts/fact_orders.sql",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_bare_target_when_running_then_applies_refactor(
    test_case: BareTargetRefactorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative_path: str
    content: str
    for relative_path, content in _PROJECT_FILES.items():
        path: Path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    exit_code: int = run_refactor_command(
        request=RefactorCommandRequest(
            command=test_case.command,
            target=test_case.target,
            new_name=test_case.new_name,
            destination=test_case.destination,
            project_dir=tmp_path,
            no_color=True,
        )
    )

    output: str = capsys.readouterr().out
    assert exit_code == 0, output
    assert test_case.expected_fragment in (tmp_path / test_case.expected_path).read_text()
    missing_path: str
    for missing_path in test_case.expected_missing_paths:
        assert not (tmp_path / missing_path).exists()


@pytest.mark.parametrize(
    "test_case",
    [
        NativeEditCountTestCase(
            description="a model rename plans its reference natively and adds migrate_from",
            command=CliCommand.RENAME,
            target="model:stg_orders",
            new_name="stg_order_lines",
            expected_native_counts={
                CompilerEngine.NATIVE.value: {"planned_edits": 1, "migration_edits": 1},
                CompilerEngine.NATIVE_PREVIEW.value: {"planned_edits": 1, "migration_edits": 1},
            },
        ),
        NativeEditCountTestCase(
            description="a column rename plans the owner output and the downstream alias natively",
            command=CliCommand.RENAME,
            target="column:stg_orders.amount",
            new_name="revenue",
            expected_native_counts={
                CompilerEngine.NATIVE.value: {"planned_edits": 3, "migration_edits": 0},
                CompilerEngine.NATIVE_PREVIEW.value: {"planned_edits": 3, "migration_edits": 0},
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_refactor_when_running_then_native_stage_plans_exact_edit_count(
    test_case: NativeEditCountTestCase,
    refactor_compiler_engine: CompilerEngine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / "project"
    relative_path: str
    content: str
    for relative_path, content in _PROJECT_FILES.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    start_recording(record_dir=tmp_path / "records", monkeypatch=monkeypatch)

    exit_code: int = run_refactor_command(
        request=RefactorCommandRequest(
            command=test_case.command,
            target=test_case.target,
            new_name=test_case.new_name,
            project_dir=project_dir,
            no_color=True,
        )
    )

    assert exit_code == 0, capsys.readouterr().out
    assert (
        refactoring_answers(record_dir=tmp_path / "records")
        == test_case.expected_native_counts[refactor_compiler_engine.value]
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
