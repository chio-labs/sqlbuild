"""Bounded discovery entry points read through the native discovery as Python's did."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.filesystem import aggregation
from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_model_files,
    discover_scenario_files,
    discover_source_files,
    discover_test_files,
)
from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    EntryPointParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    FailureCapture,
    contents_parse_outcome,
    selected_entry_point_outcome,
    tolerant_scope_outcome,
    write_project,
)

_MODEL: bytes = b'MODEL (description "Orders");\nSELECT 1 AS order_id'
_TEST: bytes = b'TEST (name "keeps_orders");\n\nSELECT 1\n'
_ENUM: bytes = b"ENUM (name tier, members [GOLD]);\n"


@pytest.mark.parametrize(
    "test_case",
    [
        EntryPointParityTestCase(
            description="valid models, tests and declarations",
            files=(
                ("models/orders.sql", _MODEL),
                ("models/marts/customers.sql", _MODEL),
                ("tests/unit/orders.sql", _TEST),
                ("tests/scenarios/orders.sql", b'SCENARIO (description "Orders");\nSELECT 1\n'),
                ("enums/tier.sql", _ENUM),
                ("sources/raw.yml", b"sources:\n  - name: raw_orders\n    description: Raw.\n"),
            ),
        ),
        EntryPointParityTestCase(
            description="unreadable and invalid files become faults",
            files=(
                ("models/a.sql", _MODEL),
                ("models/b.sql", b"MODEL ();\nSELECT '\xff'"),
                ("models/c.sql", b"SELECT 1"),
                ("tests/unit/a.sql", b"TEST (nme 1);\nSELECT 1"),
                ("tests/unit/b.sql", b"\xfe"),
                ("tests/scenarios/a.sql", b"SELECT 1"),
                ("sources/raw.yml", b"sources: [\n"),
            ),
        ),
        EntryPointParityTestCase(
            description="layout faults stay in the declaration kind that owns them",
            files=(
                ("models/orders.sql", _MODEL),
                ("_macros/money.py", b"def cents(value):\n    return value\n"),
                ("enums/tier.sql", _ENUM),
                ("models/a/_constants/_enums/x.sql", _ENUM),
                ("audits/x.sql", b""),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
@pytest.mark.parametrize(
    "outcome",
    [selected_entry_point_outcome, contents_parse_outcome],
    ids=lambda function: function.__name__,
)
def test_given_project_when_reading_through_native_entry_point_then_python_outcome_matches(
    test_case: EntryPointParityTestCase,
    outcome: Callable[..., object],
    tmp_path: Path,
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    python_capture: FailureCapture = FailureCapture()
    python: list[object] = []
    with python_capture:
        python.append(outcome(project_dir=tmp_path, native=False))

    native_capture: FailureCapture = FailureCapture()
    native: list[object] = []
    with native_capture:
        native.append(outcome(project_dir=tmp_path, native=True))

    assert ((native, str(native_capture.failure)) == (python, str(python_capture.failure))) is (
        test_case.expected_identical
    ), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        EntryPointParityTestCase(
            description="valid models, tests and declarations",
            files=(
                ("models/orders.sql", _MODEL),
                ("models/marts/customers.sql", _MODEL),
                ("tests/unit/orders.sql", _TEST),
                ("tests/scenarios/orders.sql", b'SCENARIO (description "Orders");\nSELECT 1\n'),
                ("enums/tier.sql", _ENUM),
                ("sources/raw.yml", b"sources:\n  - name: raw_orders\n    description: Raw.\n"),
            ),
        ),
        EntryPointParityTestCase(
            description="unreadable and invalid files become faults",
            files=(
                ("models/a.sql", _MODEL),
                ("models/b.sql", b"MODEL ();\nSELECT '\xff'"),
                ("models/c.sql", b"SELECT 1"),
                ("tests/unit/a.sql", b"TEST (nme 1);\nSELECT 1"),
                ("tests/unit/b.sql", b"\xfe"),
                ("tests/scenarios/a.sql", b"SELECT 1"),
                ("sources/raw.yml", b"sources: [\n"),
            ),
        ),
        EntryPointParityTestCase(
            description="layout faults stay in the declaration kind that owns them",
            files=(
                ("models/orders.sql", _MODEL),
                ("_macros/money.py", b"def cents(value):\n    return value\n"),
                ("enums/tier.sql", _ENUM),
                ("models/a/_constants/_enums/x.sql", _ENUM),
                ("audits/x.sql", b""),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_building_tolerant_scope_discovery_then_python_faults_match(
    test_case: EntryPointParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    native: object = tolerant_scope_outcome(project_dir=tmp_path)
    for name, python_function in (
        ("discover_native_model_files", discover_model_files),
        ("discover_native_test_files", discover_test_files),
        ("discover_native_scenario_files", discover_scenario_files),
        ("discover_native_source_files", discover_source_files),
        ("prepare_native_declaration_layout", lambda **_arguments: None),
    ):
        monkeypatch.setattr(aggregation, name, python_function)

    python: object = tolerant_scope_outcome(project_dir=tmp_path)

    assert (native == python) is test_case.expected_identical, test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
