"""Both compiler engines discover identical SQL model files, failures and project inputs."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.frontier._helpers.stage_capture import render_stage_capture
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    EngineSwitchParityTestCase,
    GeneratedModelParityTestCase,
    ModelDiscoveryParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    generated_model_bytes,
    model_discovery_outcome,
    write_project,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

_VALID_MODEL: bytes = b"MODEL (materialized table);\nSELECT order_id, total AS amount FROM orders"


@pytest.mark.parametrize(
    "test_case",
    [
        ModelDiscoveryParityTestCase(
            description="sorted part by part, scoped declaration trees skipped",
            files=(
                ("models/a-c.sql", _VALID_MODEL),
                ("models/a/b.sql", _VALID_MODEL),
                ("models/.hidden.sql", _VALID_MODEL),
                ("models/core/_sqlbuild/schemas/x.sql", b"not a model"),
                ("models/core/macros/helpers.sql", b"not a model"),
                ("models/notes.txt", b"ignored"),
            ),
        ),
        ModelDiscoveryParityTestCase(
            description="CRLF, CR and non-ASCII locations",
            files=(
                (
                    "models/orders.sql",
                    "MODEL (\r\n  description 'é',\r  columns (id (type INT)),\r\n);\r\n"
                    'SELECT id, "Ünit" AS ünit FROM t'.encode(),
                ),
            ),
        ),
        ModelDiscoveryParityTestCase(
            description="byte order mark before the header",
            files=(("models/orders.sql", b"\xef\xbb\xbf" + _VALID_MODEL),),
        ),
        ModelDiscoveryParityTestCase(
            description="invalid UTF-8 raises Python's decoding error",
            files=(("models/a.sql", _VALID_MODEL), ("models/b.sql", b"MODEL ();\nSELECT '\xff'")),
        ),
        ModelDiscoveryParityTestCase(
            description="a directory named like a model is read and fails",
            files=(("models/a.sql", _VALID_MODEL),),
            directories=("models/b.sql",),
        ),
        ModelDiscoveryParityTestCase(
            description="the first failing file in order wins",
            files=(
                ("models/a.sql", _VALID_MODEL),
                ("models/b.sql", b"MODEL (tagz [x]);\nSELECT 1"),
                ("models/c.sql", b"SELECT 1"),
            ),
        ),
        ModelDiscoveryParityTestCase(
            description="model-local enum declarations fail after the header checks",
            files=(("models/a.sql", b"MODEL (enums [a]);\nSELECT 1"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_files_when_discovering_with_each_engine_then_outcomes_match(
    test_case: ModelDiscoveryParityTestCase, tmp_path: Path
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    for directory in test_case.directories:
        (tmp_path / directory).mkdir(parents=True)

    python: object = model_discovery_outcome(project_dir=tmp_path, native=False)
    native: object = model_discovery_outcome(project_dir=tmp_path, native=True)

    assert (native == python) is test_case.expected_identical


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedModelParityTestCase(
            description="mixed headers and projections", seed=61, case_count=400
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_model_files_when_discovering_with_each_engine_then_outcomes_match(
    test_case: GeneratedModelParityTestCase, tmp_path: Path
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    contents: list[bytes] = [generated_model_bytes(rng=rng) for _ in range(test_case.case_count)]
    expected: list[object] = []
    actual: list[object] = []
    for index, data in enumerate(contents):
        project_dir: Path = tmp_path / f"case_{index}"
        write_project(project_dir=project_dir, files=(("models/orders.sql", data),))
        expected.append(model_discovery_outcome(project_dir=project_dir, native=False))
        actual.append(model_discovery_outcome(project_dir=project_dir, native=True))

    assert mismatches(inputs=list(contents), expected=expected, actual=actual) == list(
        test_case.expected_mismatches
    )


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
