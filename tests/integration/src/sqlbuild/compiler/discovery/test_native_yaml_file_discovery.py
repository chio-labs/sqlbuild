"""Engine parity for source and schema YAML files loaded natively with per-file deferral."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    NativeYamlLoadTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    native_yaml_tags_and_values,
    write_project,
)

_SOURCES: bytes = (
    b"sources:\n  - name: raw_orders\n    description: Orders feed.\n"
    b"    columns:\n      - name: order_id\n        type: INTEGER\n"
)
_BIG_HEX: str = "0x" + "f" * 4000
_BIG_OCTAL: str = "0" + "7" * 4200
_BIG_BINARY: str = "0b" + "1" * 4200
_SEED: bytes = (
    b"seeds:\n  - name: channels\n    description: Channels.\n"
    b"    columns:\n      - name: id\n        type: INTEGER\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeYamlLoadTestCase(
            description="big hexadecimal, octal and binary integers load as values and explicit keys",
            files=(
                (
                    "sources/a.yml",
                    (
                        f"sources:\n  - name: orders\n    meta:\n      hex: {_BIG_HEX}\n"
                        f"      octal: {_BIG_OCTAL}\n      binary: {_BIG_BINARY}\n"
                        f"      ? {_BIG_HEX}\n      : key\n      ? {_BIG_BINARY}\n      : key\n"
                    ).encode(),
                ),
            ),
            expected_native_tags=("ok",),
        ),
        NativeYamlLoadTestCase(
            description="an implicit key beyond the simple-key limit is unsupported",
            files=(("sources/a.yml", f"sources: []\nmeta: {{{_BIG_HEX}: key}}\n".encode()),),
            expected_native_tags=("error",),
        ),
        NativeYamlLoadTestCase(
            description="an invalid file fails on its own and a later big integer still loads",
            files=(
                ("sources/a.yml", b"sources: [\n"),
                ("sources/b.yml", f"sources: []\nmeta: {{v: {_BIG_HEX}}}\n".encode()),
            ),
            expected_native_tags=("error", "ok"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_big_integers_when_loading_natively_then_values_match_libyaml(
    test_case: NativeYamlLoadTestCase, tmp_path: Path
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)

    tags, values_match = native_yaml_tags_and_values(
        project_dir=tmp_path, relative_paths=[path for path, _contents in test_case.files]
    )

    assert (tags, values_match) == (
        list(test_case.expected_native_tags),
        True,
    ), test_case.description
