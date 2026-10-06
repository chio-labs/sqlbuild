"""Compare the native TOML loader with `tomllib` on seeded and repository documents."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    GeneratedDocumentOracleTestCase,
    HostileDocumentOracleTestCase,
    RepositoryFileOracleTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    DEFERRED,
    HOSTILE_TOML_DOCUMENTS,
    TOML_DOCUMENT_GENERATORS,
    deferred_valid_count,
    harmful_mismatches,
    native_toml_outcome,
    python_toml_outcome,
    repository_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedDocumentOracleTestCase(
            description="tables, dotted keys, arrays of tables, strings, numbers and datetimes",
            generator="toml",
            seed=51,
            case_count=5000,
            expected_maximum_deferred=350,
        ),
        GeneratedDocumentOracleTestCase(
            description="tables, arrays of tables, inline tables and dotted keys reopening namespaces",
            generator="toml namespaces",
            seed=52,
            case_count=5000,
            expected_maximum_deferred=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_toml_when_loading_natively_then_values_match_tomllib(
    test_case: GeneratedDocumentOracleTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    generate: Callable[[random.Random], str] = TOML_DOCUMENT_GENERATORS[test_case.generator]
    texts: list[str] = [generate(rng) for _ in range(test_case.case_count)]

    expected: list[object] = [python_toml_outcome(text=text) for text in texts]
    actual: list[object] = [native_toml_outcome(text=text) for text in texts]

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
            description="repository TOML files", pattern="**/*.toml", expected_minimum_files=8
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repository_toml_files_when_loading_natively_then_values_match_tomllib(
    test_case: RepositoryFileOracleTestCase,
) -> None:
    paths: list[Path] = repository_files(pattern=test_case.pattern)
    texts: list[str] = [path.read_text(encoding="utf-8") for path in paths]

    expected: list[object] = [python_toml_outcome(text=text) for text in texts]
    actual: list[object] = [native_toml_outcome(text=text) for text in texts]

    assert len(paths) >= test_case.expected_minimum_files
    assert deferred_valid_count(expected=expected, actual=actual) == test_case.expected_deferred
    assert harmful_mismatches(
        inputs=list(map(str, paths)), expected=expected, actual=actual
    ) == list(test_case.expected_mismatches)


@pytest.mark.parametrize(
    "test_case",
    [
        HostileDocumentOracleTestCase(
            description="ten thousand nested arrays", document="deep arrays"
        ),
        HostileDocumentOracleTestCase(
            description="ten thousand nested inline tables", document="deep inline tables"
        ),
        HostileDocumentOracleTestCase(
            description="a dotted key with a hundred thousand segments", document="long dotted key"
        ),
        HostileDocumentOracleTestCase(
            description="a table header with a hundred thousand segments",
            document="long table header",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_hostile_toml_when_loading_natively_then_reader_defers_quickly(
    test_case: HostileDocumentOracleTestCase,
) -> None:
    text: str = HOSTILE_TOML_DOCUMENTS[test_case.document]()

    started: float = time.perf_counter()
    outcome: object = native_toml_outcome(text=text)
    elapsed: float = time.perf_counter() - started

    assert (outcome == DEFERRED, elapsed < test_case.expected_maximum_seconds) == (
        test_case.expected_deferred,
        True,
    ), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
