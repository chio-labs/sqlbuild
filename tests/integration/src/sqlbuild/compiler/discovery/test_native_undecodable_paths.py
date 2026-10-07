"""Callers that tolerate bad files fault only the files whose read paths are not UTF-8."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    CollidingNamesTestCase,
    UndecodablePathToleranceTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    declared_enums_outcome,
    description_inputs_outcome,
    selected_contract_outcome,
    tolerant_scope_fault_outcome,
    write_project,
)

_MODEL: bytes = b"MODEL ();\nSELECT 1 AS id"
_TEST: bytes = b'TEST (name "keeps_orders");\nSELECT 1\n'
_SOURCE: bytes = b"sources:\n  - name: raw_orders\n"
_FILES: tuple[tuple[str, bytes], ...] = (
    ("models/orders.sql", _MODEL),
    (os.fsdecode(b"models/caf\xe9.sql"), _MODEL),
    (os.fsdecode(b"models/notes\xe9.txt"), b"x"),
    ("tests/unit/orders.sql", _TEST),
    (os.fsdecode(b"tests/unit/old\xe9/orders.sql"), _TEST),
    ("sources/raw.yml", _SOURCE),
)
_BAD_SOURCE: tuple[str, bytes] = (os.fsdecode(b"sources/caf\xe9.yml"), _SOURCE)
_RENAME: str = " is not valid UTF-8; rename it so SQLBuild can read it"
_ORDER_STATUS: bytes = b"ENUM (name order_status, members [PLACED]);\n"
_TIER: bytes = b"ENUM (name tier, members [GOLD]);\n"
_READERS: dict[str, Callable[..., tuple[object, ...]]] = {
    "scope": tolerant_scope_fault_outcome,
    "descriptions": description_inputs_outcome,
    "selected contracts": selected_contract_outcome,
}


@pytest.mark.parametrize(
    "test_case",
    [
        UndecodablePathToleranceTestCase(
            description="scope discovery faults each unreadable path and keeps the rest",
            reader="scope",
            files=(*_FILES, _BAD_SOURCE),
            expected_models=("models/orders.sql",),
            expected_sources=("sources/raw.yml",),
            expected_faults=(
                (_FILES[1][0], f"Project path ./models/caf\\xe9.sql{_RENAME}"),
                (_BAD_SOURCE[0], f"Project path ./sources/caf\\xe9.yml{_RENAME}"),
                (_FILES[4][0], f"Project path ./tests/unit/old\\xe9/orders.sql{_RENAME}"),
            ),
        ),
        UndecodablePathToleranceTestCase(
            description="a valid name is not blamed for a raw sibling with the same lossy name",
            reader="scope",
            files=(
                ("models/orders.sql", _MODEL),
                ("models/st\ufffd.sql", b"MODEL ();\nSELECT 2 AS id"),
                (os.fsdecode(b"models/st\xe8.sql"), b"garbage"),
            ),
            expected_models=("models/orders.sql", "models/st\ufffd.sql"),
            expected_sources=(),
            expected_faults=(
                (
                    os.fsdecode(b"models/st\xe8.sql"),
                    f"Project path ./models/st\\xe8.sql{_RENAME}",
                ),
            ),
        ),
        UndecodablePathToleranceTestCase(
            description="model descriptions skip an unreadable model path",
            reader="descriptions",
            files=(*_FILES, _BAD_SOURCE),
            expected_models=("models/orders.sql",),
            expected_sources=(),
        ),
        UndecodablePathToleranceTestCase(
            description="selected contracts never read an unselected model path",
            reader="selected contracts",
            files=_FILES,
            expected_models=("models/orders.sql",),
            expected_sources=("sources/raw.yml",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_undecodable_paths_when_discovering_tolerantly_then_each_read_path_faults_alone(
    test_case: UndecodablePathToleranceTestCase, tmp_path: Path
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)

    outcome: tuple[object, ...] = _READERS[test_case.reader](project_dir=tmp_path)

    assert outcome == (
        test_case.expected_models,
        test_case.expected_sources,
        test_case.expected_faults,
    ), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        CollidingNamesTestCase(
            description="an enum file whose name is not UTF-8 is read by its real name",
            files=((os.fsdecode(b"enums/st\xe9.sql"), _ORDER_STATUS),),
            expected_enums=((os.fsdecode(b"enums/st\xe9.sql"), ("order_status",)),),
        ),
        CollidingNamesTestCase(
            description="enum files sharing a lossy name each keep their own declarations",
            files=(
                (os.fsdecode(b"enums/st\xe9.sql"), _ORDER_STATUS),
                (os.fsdecode(b"enums/st\xe8.sql"), _TIER),
            ),
            expected_enums=(
                (os.fsdecode(b"enums/st\xe8.sql"), ("tier",)),
                (os.fsdecode(b"enums/st\xe9.sql"), ("order_status",)),
            ),
        ),
        CollidingNamesTestCase(
            description="a valid replacement-character name is not replaced by a raw sibling",
            files=(
                ("enums/st\ufffd.sql", _ORDER_STATUS),
                (os.fsdecode(b"enums/st\xe8.sql"), _TIER),
            ),
            expected_enums=(
                (os.fsdecode(b"enums/st\xe8.sql"), ("tier",)),
                ("enums/st\ufffd.sql", ("order_status",)),
            ),
        ),
        CollidingNamesTestCase(
            description="directories sharing a lossy name each keep their own files",
            files=(
                (os.fsdecode(b"models/a\xe9/_enums/x.sql"), _ORDER_STATUS),
                (os.fsdecode(b"models/a\xe8/_enums/y.sql"), _TIER),
            ),
            expected_enums=(
                (os.fsdecode(b"models/a\xe8/_enums/y.sql"), ("tier",)),
                (os.fsdecode(b"models/a\xe9/_enums/x.sql"), ("order_status",)),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_names_sharing_a_lossy_spelling_when_discovering_then_each_file_keeps_its_identity(
    test_case: CollidingNamesTestCase, tmp_path: Path
) -> None:
    write_project(project_dir=tmp_path, files=(("models/orders.sql", _MODEL), *test_case.files))

    outcome: tuple[object, ...] = declared_enums_outcome(project_dir=tmp_path)

    assert outcome == (test_case.expected_enums, test_case.expected_models), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
