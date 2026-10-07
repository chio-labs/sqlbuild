"""Both compiler engines discover identical SQL model files, failures and project inputs."""

from __future__ import annotations

import os
import random
import sys
import unicodedata
from pathlib import Path

import pytest

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.native.model_files import (
    discover_native_model_files,
)
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.frontier._helpers.stage_capture import render_stage_capture
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    EngineSwitchParityTestCase,
    GeneratedModelParityTestCase,
    ModelDiscoveryParityTestCase,
    NativeDeferralTestCase,
    SharedSnapshotTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    CallCounter,
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


@pytest.mark.parametrize(
    "test_case",
    [
        NativeDeferralTestCase(
            description="matching Unicode data and a UTF-8 root run natively",
            project_name="orders",
            expected_native_calls=1,
        ),
        NativeDeferralTestCase(
            description="different Unicode data defers to Python",
            project_name="orders",
            unidata_version="0.0.0",
            expected_native_calls=0,
        ),
        NativeDeferralTestCase(
            description="another supported Python and its Unicode data run natively",
            project_name="orders",
            unidata_version="16.0.0",
            python_version=(3, 14),
            expected_native_calls=1,
        ),
        NativeDeferralTestCase(
            description="an unreleased Python defers to Python",
            project_name="orders",
            unidata_version="16.0.0",
            python_version=(3, 15),
            expected_native_calls=0,
        ),
        NativeDeferralTestCase(
            description="a non-UTF-8 project root defers to Python",
            project_name=os.fsdecode(b"orders\xff"),
            expected_native_calls=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_runtime_and_root_when_discovering_natively_then_python_runs_where_native_cannot_match(
    test_case: NativeDeferralTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir: Path = tmp_path / test_case.project_name
    write_project(project_dir=project_dir, files=(("models/orders.sql", _VALID_MODEL),))
    python: object = model_discovery_outcome(project_dir=project_dir, native=False)
    counter: CallCounter = CallCounter(_native.discover_model_files)
    monkeypatch.setattr(_native, "discover_model_files", counter)
    monkeypatch.setattr(unicodedata, "unidata_version", test_case.unidata_version)
    monkeypatch.setattr(sys, "version_info", (*test_case.python_version, 0, "final", 0))

    native: object = model_discovery_outcome(project_dir=project_dir, native=True)

    assert (native, counter.calls) == (python, test_case.expected_native_calls)


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
