"""Both compiler engines discover identical SQL model files, failures and project inputs."""

from __future__ import annotations

import os
import sys
import unicodedata
from pathlib import Path

import pytest

from sqlbuild import _native
from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.discovery._helpers.native.model_files import (
    discover_native_model_files,
)
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.compiler.frontier._helpers.stage_capture import render_stage_capture
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    EngineSwitchParityTestCase,
    NativeRuntimeTestCase,
    SharedSnapshotTestCase,
    UnsupportedPythonCommandTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    FailureCapture,
    write_project,
)

_VALID_MODEL: bytes = b"MODEL (materialized table);\nSELECT order_id, total AS amount FROM orders"


@pytest.mark.parametrize(
    "test_case",
    [
        EngineSwitchParityTestCase(
            description="models, model-local declarations and a macro",
            files=(
                ("models/orders.sql", _VALID_MODEL),
                (
                    "models/marts/customers.sql",
                    b"MODEL (enums (_tier [GOLD, SILVER]));\nSELECT 1 AS id",
                ),
                ("macros/money.py", b"def cents(value):\n    return f'{value} * 100'\n"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_discovering_through_the_engine_switch_then_inputs_match(
    test_case: EngineSwitchParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, "python")
    python: str = render_stage_capture(discover_project_inputs(project_dir=tmp_path))
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, "native")
    native: str = render_stage_capture(discover_project_inputs(project_dir=tmp_path))

    assert (native == python) is test_case.expected_identical


@pytest.mark.parametrize(
    "test_case",
    [
        NativeRuntimeTestCase(
            description="the running Python and a UTF-8 root run natively",
            project_name="orders",
            expected_models=1,
        ),
        NativeRuntimeTestCase(
            description="another supported Python and its Unicode data run natively",
            project_name="orders",
            unidata_version="16.0.0",
            python_version=(3, 14),
            expected_models=1,
        ),
        NativeRuntimeTestCase(
            description="unknown Unicode data fails naming the supported versions",
            project_name="orders",
            unidata_version="0.0.0",
            expected_models=0,
            expected_error="UnsupportedPythonError",
            expected_message="This SQLBuild release supports Python 3.12, 3.13 and 3.14, not Python",
        ),
        NativeRuntimeTestCase(
            description="an unreleased Python fails naming its version",
            project_name="orders",
            unidata_version="16.0.0",
            python_version=(3, 15),
            expected_models=0,
            expected_error="UnsupportedPythonError",
            expected_message="not Python 3.15 (Unicode 16.0.0); run sqb with a supported Python",
        ),
        NativeRuntimeTestCase(
            description="a non-UTF-8 project root fails showing the path lossily",
            project_name=os.fsdecode(b"orders\xff"),
            expected_models=0,
            expected_error="ProjectPathError",
            expected_message="orders\\xff is not valid UTF-8; move the project to a directory",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_and_root_when_discovering_natively_then_supported_runs_and_others_fail(
    test_case: NativeRuntimeTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir: Path = tmp_path / test_case.project_name
    write_project(project_dir=project_dir, files=(("models/orders.sql", _VALID_MODEL),))
    monkeypatch.setattr(unicodedata, "unidata_version", test_case.unidata_version)
    monkeypatch.setattr(sys, "version_info", (*test_case.python_version, 0, "final", 0))
    capture: FailureCapture = FailureCapture()
    models: list[DiscoveredSqlModelFile] = []

    with capture:
        models.extend(
            discover_native_model_files(
                project_dir=project_dir,
                extract_implicit_alias_columns=True,
                extract_output_column_locations=True,
            )
        )

    assert (
        len(models),
        type(capture.failure).__name__,
        test_case.expected_message in str(capture.failure),
    ) == (test_case.expected_models, test_case.expected_error, True), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        SharedSnapshotTestCase(
            description="a schema file created after the model walk stays unseen",
            created_file="models/marts/schema.yml",
            pattern="schema.yml",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_model_walk_when_globbing_models_later_in_the_pass_then_the_walk_is_shared(
    test_case: SharedSnapshotTestCase, tmp_path: Path
) -> None:
    write_project(project_dir=tmp_path, files=(("models/marts/orders.sql", _VALID_MODEL),))
    with DirectorySnapshot.scope(project_dir=tmp_path) as snapshot:
        _ = discover_native_model_files(
            project_dir=tmp_path,
            extract_implicit_alias_columns=True,
            extract_output_column_locations=True,
        )
        _ = (tmp_path / test_case.created_file).write_text("models: []\n", encoding="utf-8")
        matches: tuple[Path, ...] = snapshot.rglob(
            root=tmp_path / "models", pattern=test_case.pattern
        )

    assert tuple(path.relative_to(tmp_path).as_posix() for path in matches) == (
        test_case.expected_matches
    )


@pytest.mark.parametrize(
    "test_case",
    [
        UnsupportedPythonCommandTestCase(
            description="compile reports the coded error without a traceback",
            command=("compile",),
            expected_exit_code=1,
            expected_error="error[D017]: This SQLBuild release supports Python 3.12, 3.13 and 3.14",
        ),
        UnsupportedPythonCommandTestCase(
            description="tolerant scope discovery still refuses the Python",
            command=("scope", "models/orders.sql"),
            expected_exit_code=1,
            expected_error="error[D017]: This SQLBuild release supports Python 3.12, 3.13 and 3.14",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_python_when_running_command_then_coded_error_is_printed(
    test_case: UnsupportedPythonCommandTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_project(project_dir=tmp_path, files=(("models/orders.sql", _VALID_MODEL),))
    monkeypatch.setattr(_native, "native_text_supported", lambda *_arguments: False)
    _ = capsys.readouterr()

    exit_code: int = main(["--project-dir", str(tmp_path), "--no-color", *test_case.command])

    error: str = capsys.readouterr().err
    assert (exit_code, test_case.expected_error in error, "Traceback" in error) == (
        test_case.expected_exit_code,
        True,
        False,
    ), error
