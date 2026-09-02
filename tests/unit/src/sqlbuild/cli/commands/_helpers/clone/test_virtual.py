from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.commands._helpers.clone import virtual
from sqlbuild.cli.commands.models import CloneCommandRequest, CloneInvocation
from tests.unit.src.sqlbuild.cli.commands._helpers.clone._test_types import (
    VirtualCloneLifecycleCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.clone.helpers import build_virtual_clone_result


@pytest.mark.parametrize(
    "test_case",
    (
        VirtualCloneLifecycleCase(
            "missing result reports errors",
            1,
            0,
            1,
            "Clone finished with errors.",
            "Cloned virtual environment.",
        ),
        VirtualCloneLifecycleCase(
            "skipped locked result reports success",
            0,
            1,
            0,
            "Cloned virtual environment.",
            "Clone finished with errors.",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_virtual_clone_result_when_executed_then_exit_and_lifecycle_match(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    test_case: VirtualCloneLifecycleCase,
) -> None:
    monkeypatch.setattr(
        virtual,
        "run_virtual_clone",
        lambda **_: build_virtual_clone_result(
            missing_count=test_case.missing_count,
            skipped_count=test_case.skipped_count,
        ),
    )
    monkeypatch.setattr(virtual, "resolve_target_connection_config", lambda **_: {})
    monkeypatch.setattr(virtual, "resolve_external_sql_reference_resolver", lambda **_: None)
    monkeypatch.setattr(virtual, "render_virtual_clone_output", lambda **_: None)
    monkeypatch.setattr(virtual, "write_execution_json_output", lambda **_: None)
    stream: StringIO = StringIO()

    exit_code: int = virtual.execute_virtual_clone(
        request=CloneCommandRequest(
            project_dir=tmp_path,
            no_color=True,
            no_sql_validation=False,
            origin_target_name="prod",
            destination_target_name="dev",
            hard_copy=False,
            skip_locked=test_case.skipped_count > 0,
        ),
        invocation=CloneInvocation(
            effective_project_dir=tmp_path,
            discovered_inputs=Mock(),
            adapter_name="duckdb",
            adapter=DuckDbAdapter(),
            destination_target_name="dev",
            use_color=False,
            progress_stream=stream,
        ),
    )

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_progress_fragment in stream.getvalue()
    assert test_case.unexpected_progress_fragment not in stream.getvalue()
