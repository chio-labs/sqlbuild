"""Compare the native YAML loader with PyYAML `safe_load` on seeded and repository documents."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    GeneratedDocumentOracleTestCase,
    HostileDocumentOracleTestCase,
    LargeDocumentOracleTestCase,
    RepositoryFileOracleTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    DEFERRED,
    HOSTILE_YAML_DOCUMENTS,
    LARGE_YAML_DOCUMENTS,
    YAML_DOCUMENT_GENERATORS,
    deferred_valid_count,
    expected_yaml_outcome,
    harmful_mismatches,
    native_yaml_outcome,
    python_yaml_outcome,
    repository_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedDocumentOracleTestCase(
            description="near-miss plain, quoted and tagged scalars",
            generator="scalars",
            seed=41,
            case_count=4000,
            expected_maximum_deferred=10,
        ),
        GeneratedDocumentOracleTestCase(
            description="anchors, aliases, merge keys, chomped block scalars and comments",
            generator="anchors",
            seed=42,
            case_count=1500,
            expected_maximum_deferred=20,
        ),
        GeneratedDocumentOracleTestCase(
            description="keys straddling the 1024-character simple-key limit",
            generator="long keys",
            seed=44,
            case_count=600,
            expected_maximum_deferred=400,
        ),
        GeneratedDocumentOracleTestCase(
            description="documents written by PyYAML's safe dumper in random styles",
            generator="dumped",
            seed=43,
            case_count=1500,
            expected_maximum_deferred=5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_yaml_when_loading_natively_then_values_match_both_pyyaml_loaders(
    test_case: GeneratedDocumentOracleTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    generate: Callable[[random.Random], str] = YAML_DOCUMENT_GENERATORS[test_case.generator]
    texts: list[str] = [generate(rng) for _ in range(test_case.case_count)]

    expected: list[object] = [expected_yaml_outcome(text=text) for text in texts]
    actual: list[object] = [native_yaml_outcome(text=text) for text in texts]

    assert (
        deferred_valid_count(expected=expected, actual=actual)
        <= test_case.expected_maximum_deferred
    )
    assert harmful_mismatches(inputs=list(texts), expected=expected, actual=actual) == list(
        test_case.expected_mismatches
    )


@pytest.mark.parametrize(
    "test_case",
    [
        RepositoryFileOracleTestCase(
            description="repository YAML files", pattern="**/*.yml", expected_minimum_files=10
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repository_yaml_files_when_loading_natively_then_values_match_both_loaders(
    test_case: RepositoryFileOracleTestCase,
) -> None:
    paths: list[Path] = repository_files(pattern=test_case.pattern)
    texts: list[str] = [path.read_text(encoding="utf-8") for path in paths]

    expected: list[object] = [expected_yaml_outcome(text=text) for text in texts]
    actual: list[object] = [native_yaml_outcome(text=text) for text in texts]

    assert len(paths) >= test_case.expected_minimum_files
    assert deferred_valid_count(expected=expected, actual=actual) == test_case.expected_deferred
    assert harmful_mismatches(
        inputs=list(map(str, paths)), expected=expected, actual=actual
    ) == list(test_case.expected_mismatches)


@pytest.mark.parametrize(
    "test_case",
    [
        HostileDocumentOracleTestCase(
            description="a ten thousand link alias chain", document="alias chain"
        ),
        HostileDocumentOracleTestCase(
            description="billion laughs with twelve levels", document="billion laughs"
        ),
        HostileDocumentOracleTestCase(
            description="merge keys doubling over thirty levels", document="merge chain"
        ),
        HostileDocumentOracleTestCase(
            description="a hundred thousand nested flow sequences", document="deep flow"
        ),
        HostileDocumentOracleTestCase(
            description="a hundred thousand nested block sequences", document="deep block"
        ),
        HostileDocumentOracleTestCase(
            description="an integer beyond Python's string conversion limit",
            document="long integer",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_hostile_yaml_when_loading_natively_then_reader_defers_quickly(
    test_case: HostileDocumentOracleTestCase,
) -> None:
    text: str = HOSTILE_YAML_DOCUMENTS[test_case.document]()

    started: float = time.perf_counter()
    outcome: object = native_yaml_outcome(text=text)
    elapsed: float = time.perf_counter() - started

    assert (outcome == DEFERRED, elapsed < test_case.expected_maximum_seconds) == (
        test_case.expected_deferred,
        True,
    ), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        LargeDocumentOracleTestCase(
            description="a hundred thousand keys in one flow mapping line", document="flow mapping"
        ),
        LargeDocumentOracleTestCase(
            description="two hundred thousand items in one flow sequence line",
            document="flow sequence",
        ),
        LargeDocumentOracleTestCase(
            description="fifty thousand anchored items in one flow sequence line",
            document="anchored flow sequence",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_large_single_line_yaml_when_loading_natively_then_time_is_linear_and_values_match(
    test_case: LargeDocumentOracleTestCase,
) -> None:
    text: str = LARGE_YAML_DOCUMENTS[test_case.document]()
    expected: object = python_yaml_outcome(text=text, loader=yaml.CSafeLoader)

    started: float = time.perf_counter()
    actual: object = native_yaml_outcome(text=text)
    elapsed: float = time.perf_counter() - started

    assert (actual, elapsed < test_case.expected_maximum_seconds) == (expected, True), (
        test_case.description
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
