"""Engine parity for the declaration layout native discovery walks and validates."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    EngineSwitchParityTestCase,
    GeneratedLayoutParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    generated_layout_files,
    native_layout_outcome,
    python_layout_outcome,
    stage_outcome,
    write_project,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

_AUDIT: bytes = b'AUDIT ();\n\nSELECT *\nFROM __ref("@model")\nWHERE NOT (@expression)\n'
_SCHEMA: bytes = (
    b'SCHEMA (\n  name order_shape,\n  description "Order shape",\n'
    b"  columns (\n    id (type INTEGER),\n  ),\n);\n"
)
_HOOK: bytes = b'HOOK (\n  description "Record a refresh"\n);\n\nSELECT 1 AS refreshed\n'
_MACRO: bytes = b"def cents(value):\n    return f'{value} * 100'\n"
_MODEL: bytes = b'MODEL (description "Orders");\nSELECT 1 AS order_id'


@pytest.mark.parametrize(
    "test_case",
    [
        EngineSwitchParityTestCase(
            description="global, inherited, local and grouped declarations of every kind",
            files=(
                ("models/marts/orders.sql", _MODEL),
                ("macros/money.py", _MACRO),
                ("macros/__init__.py", b""),
                ("enums/status.sql", b"ENUM (name order_status, members [PLACED]);\n"),
                ("models/marts/_enums/tier.sql", b"ENUM (name tier, members [GOLD]);\n"),
                ("models/marts/_sqlbuild/constants/limits.sql", b"CONSTANT (name cap, value 3);\n"),
                ("models/marts/_sqlbuild/_audits/generic/is_true.sql", _AUDIT),
                ("models/marts/_sqlbuild/_schemas/order_shape.sql", _SCHEMA),
                ("models/marts/_sqlbuild/hooks/sql/record_refresh.sql", _HOOK),
                ("audits/generic/is_true.sql", _AUDIT),
                ("schemas/order_shape.sql", _SCHEMA),
                ("hooks/sql/_private.sql", _HOOK),
                ("functions/sql/_macros/helpers.py", _MACRO),
                ("seeds/channels.csv", b"id\n1\n"),
            ),
        ),
        EngineSwitchParityTestCase(
            description="a nested declaration root fails with Python's error",
            files=(("models/marts/_enums/macros/money.py", _MACRO),),
        ),
        EngineSwitchParityTestCase(
            description="an unsupported audit role entry fails with Python's error",
            files=(("models/marts/orders.sql", _MODEL), ("audits/is_true.sql", _AUDIT)),
        ),
        EngineSwitchParityTestCase(
            description="an unreadable declaration file fails with Python's read error",
            files=(("enums/status.sql", b"\xff"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_declaration_layout_when_discovering_through_the_engine_switch_then_inputs_match(
    test_case: EngineSwitchParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    python: object = stage_outcome(project_dir=tmp_path, engine="python", monkeypatch=monkeypatch)

    native: object = stage_outcome(project_dir=tmp_path, engine="native", monkeypatch=monkeypatch)

    assert (native == python) is test_case.expected_identical, test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedLayoutParityTestCase(
            description="seeded layouts over every declaration role",
            seed=20261007,
            count=400,
            expected_minimum_valid=60,
            expected_minimum_invalid=60,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_layouts_when_validating_natively_then_facts_and_failures_match_python(
    test_case: GeneratedLayoutParityTestCase, tmp_path: Path
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    project_dirs: list[Path] = [tmp_path / f"project_{index}" for index in range(test_case.count)]
    for project_dir in project_dirs:
        write_project(project_dir=project_dir, files=generated_layout_files(rng=rng))
    expected: list[tuple[object, object]] = [
        python_layout_outcome(project_dir=path) for path in project_dirs
    ]

    actual: list[tuple[object, object]] = [
        native_layout_outcome(project_dir=path) for path in project_dirs
    ]

    valid: int = sum(None not in outcome for outcome in expected)
    inputs: list[object] = [path.name for path in project_dirs]
    expected_outcomes: list[object] = [*expected]
    actual_outcomes: list[object] = [*actual]
    assert (
        mismatches(inputs=inputs, expected=expected_outcomes, actual=actual_outcomes),
        valid >= test_case.expected_minimum_valid,
        test_case.count - valid >= test_case.expected_minimum_invalid,
    ) == (list(test_case.expected_mismatches), True, True), test_case.description
