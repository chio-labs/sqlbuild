"""Repository, hostile and large YAML documents through the native YAML 1.2 loader."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    HostileDocumentOracleTestCase,
    LargeDocumentOracleTestCase,
    RepositoryFileOracleTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    DEFERRED,
    HOSTILE_YAML_DOCUMENTS,
    LARGE_YAML_DOCUMENTS,
    canonical,
    native_yaml_outcome,
    repository_files,
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
def test_given_repository_yaml_files_when_loading_natively_then_every_file_loads(
    test_case: RepositoryFileOracleTestCase,
) -> None:
    paths: list[Path] = repository_files(pattern=test_case.pattern)

    rejected: list[str] = [
        str(path)
        for path in filter(
            lambda path: native_yaml_outcome(text=path.read_text(encoding="utf-8")) == DEFERRED,
            paths,
        )
    ]

    assert len(paths) >= test_case.expected_minimum_files
    assert len(rejected) == test_case.expected_deferred, rejected


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
            description="an integer beyond the 4300 digits Python converts",
            document="long integer",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_hostile_yaml_when_loading_natively_then_reader_refuses_quickly(
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
            description="a hundred thousand keys in one flow mapping line",
            document="flow mapping",
            expected_value={f"k{index}": index for index in range(100_000)},
        ),
        LargeDocumentOracleTestCase(
            description="two hundred thousand items in one flow sequence line",
            document="flow sequence",
            expected_value=[1] * 200_000,
        ),
        LargeDocumentOracleTestCase(
            description="fifty thousand anchored items in one flow sequence line",
            document="anchored flow sequence",
            expected_value=[f"x{index}" for index in range(50_000)],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_large_single_line_yaml_when_loading_natively_then_time_is_linear_and_values_match(
    test_case: LargeDocumentOracleTestCase,
) -> None:
    text: str = LARGE_YAML_DOCUMENTS[test_case.document]()

    started: float = time.perf_counter()
    actual: object = native_yaml_outcome(text=text)
    elapsed: float = time.perf_counter() - started

    assert actual == canonical(test_case.expected_value), test_case.description
    assert elapsed < test_case.expected_maximum_seconds, test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
