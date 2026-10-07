"""Engine parity for source and schema YAML files loaded natively with per-file deferral."""

from __future__ import annotations

import random
import unicodedata
from pathlib import Path

import pytest

import sqlbuild._native as _native
from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    EngineSwitchParityTestCase,
    FactCacheFallbackTestCase,
    GeneratedYamlFileParityTestCase,
    NativeYamlLoadTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    fact_cache_keys,
    generated_seed_declaration,
    generated_source_document,
    native_yaml_tags_and_values,
    stage_outcome,
    write_project,
    yaml_discovery_outcome,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

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
        GeneratedYamlFileParityTestCase(
            description="seeded source and seed declarations in random YAML styles",
            seed=81,
            case_count=800,
            expected_minimum_parsed=60,
            expected_minimum_failed=100,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_yaml_files_when_discovering_with_each_engine_then_outcomes_match(
    test_case: GeneratedYamlFileParityTestCase, tmp_path: Path
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    files: list[tuple[tuple[str, bytes], ...]] = [
        (
            ("sources/orders.yml", generated_source_document(rng=rng).encode("utf-8")),
            ("seeds/channels.yml", generated_seed_declaration(rng=rng).encode("utf-8")),
            ("seeds/channels.csv", b"id,label\n1,web\n"),
        )
        for _ in range(test_case.case_count)
    ]
    project_dirs: list[Path] = [tmp_path / f"case_{index}" for index in range(len(files))]
    for project_dir, project_files in zip(project_dirs, files, strict=True):
        write_project(project_dir=project_dir, files=project_files)
    expected: list[object] = [
        yaml_discovery_outcome(project_dir=project_dir, native=False)
        for project_dir in project_dirs
    ]

    actual: list[object] = [
        yaml_discovery_outcome(project_dir=project_dir, native=True) for project_dir in project_dirs
    ]

    parsed: int = sum(isinstance(outcome, str) for outcome in expected)
    assert (
        mismatches(inputs=list(files), expected=expected, actual=actual),
        parsed >= test_case.expected_minimum_parsed,
        len(expected) - parsed >= test_case.expected_minimum_failed,
    ) == (list(test_case.expected_mismatches), True, True), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        EngineSwitchParityTestCase(
            description="sources, model schema and seed declarations",
            files=(
                ("sources/orders.yml", _SOURCES),
                ("sources/more.yaml", _SOURCES.replace(b"raw_orders", b"raw_customers")),
                ("sources/notes.txt", b"ignored"),
                ("models/orders.sql", b'MODEL (description "Orders");\nSELECT 1 AS order_id'),
                ("models/marts/schema.yml", b"models: []\n"),
                ("models/marts/_sqlbuild/schemas/schema.yml", b"models: []\n"),
                ("seeds/channels.yml", _SEED),
                ("seeds/channels.csv", b"id\n1\n"),
            ),
        ),
        EngineSwitchParityTestCase(
            description="a Python-only tag and invalid YAML load in Python with its error",
            files=(
                ("sources/a.yml", b"sources: []\nextra: !!set {a: null}\n"),
                ("sources/b.yml", b"sources: [\n"),
            ),
        ),
        EngineSwitchParityTestCase(
            description="an unreadable source file fails with Python's read error",
            files=(("sources/a.yml", b"sources: []\n# \xff\n"),),
        ),
        EngineSwitchParityTestCase(
            description="a directory named like a source file fails as Python reads it",
            files=(("sources/folder.yml/inner.txt", b""),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_yaml_files_when_discovering_through_the_engine_switch_then_inputs_match(
    test_case: EngineSwitchParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    python: object = stage_outcome(project_dir=tmp_path, engine="python", monkeypatch=monkeypatch)

    native: object = stage_outcome(project_dir=tmp_path, engine="native", monkeypatch=monkeypatch)

    assert (native == python) is test_case.expected_identical, test_case.description


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
            description="an implicit key beyond PyYAML's simple-key limit is left to Python",
            files=(("sources/a.yml", f"sources: []\nmeta: {{{_BIG_HEX}: key}}\n".encode()),),
            expected_native_tags=("load",),
        ),
        NativeYamlLoadTestCase(
            description="an earlier invalid file still fails before a later big integer",
            files=(
                ("sources/a.yml", b"sources: [\n"),
                ("sources/b.yml", f"sources: []\nmeta: {{v: {_BIG_HEX}}}\n".encode()),
            ),
            expected_native_tags=("load", "ok"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_big_integers_when_loading_natively_then_values_and_error_order_match_python(
    test_case: NativeYamlLoadTestCase, tmp_path: Path
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    python: object = yaml_discovery_outcome(project_dir=tmp_path, native=False)

    native: object = yaml_discovery_outcome(project_dir=tmp_path, native=True)
    tags, values_match = native_yaml_tags_and_values(
        project_dir=tmp_path, relative_paths=[path for path, _contents in test_case.files]
    )

    assert (native, tags, values_match) == (
        python,
        list(test_case.expected_native_tags),
        True,
    ), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        FactCacheFallbackTestCase(
            description="when native defers, Python discovery uses the fact cache as usual",
            unidata_version="0.0.0",
            expected_same_keys_as_python=True,
            expected_native_keys=2,
        ),
        FactCacheFallbackTestCase(
            description="native discovery itself reads no cached facts",
            unidata_version=_native.PYTHON_ALNUM_UNICODE_VERSION,
            expected_same_keys_as_python=False,
            expected_native_keys=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_deferral_when_discovering_sources_and_tests_then_fact_cache_is_used(
    test_case: FactCacheFallbackTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(
        project_dir=tmp_path,
        files=(
            ("sources/orders.yml", _SOURCES),
            ("tests/unit/orders.sql", b'TEST (name "keeps_orders");\nSELECT 1\n'),
        ),
    )
    python: list[tuple[str, ...]] = fact_cache_keys(project_dir=tmp_path, native=False)
    monkeypatch.setattr(unicodedata, "unidata_version", test_case.unidata_version)

    native: list[tuple[str, ...]] = fact_cache_keys(project_dir=tmp_path, native=True)

    assert ((native == python), len(native)) == (
        test_case.expected_same_keys_as_python,
        test_case.expected_native_keys,
    ), test_case.description
