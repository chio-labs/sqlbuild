from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.yml_sources import parse_sources_yml
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    ParseSourcesYamlErrorTestCase,
    ParseSourcesYamlTestCase,
)

TEST_CASES: list[ParseSourcesYamlTestCase] = [
    ParseSourcesYamlTestCase(
        description="parses sources with optional type enforcement and columns",
        contents="""
        sources:
          - name: raw_orders
            database: raw
            schema: public
            table: orders
            type_enforcement: true
            columns:
              - name: order_id
                type: VARCHAR
              - name: created_at
                type: TIMESTAMP_NTZ
          - name: raw_customers
            schema: public
            table: customers
        """,
        expected_source_names=("raw_orders", "raw_customers"),
        expected_column_names=(("order_id", "created_at"), ()),
        expected_type_enforcement_values=(True, None),
    ),
    ParseSourcesYamlTestCase(
        description="allows empty sources files with no declarations",
        contents="{}\n",
        expected_source_names=(),
        expected_column_names=(),
        expected_type_enforcement_values=(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_sources_yaml_variants_when_parsing_then_it_returns_expected_raw_metadata(
    test_case: ParseSourcesYamlTestCase,
) -> None:
    source_entries: tuple[SourceEntry, ...] = parse_sources_yml(
        test_case.contents, Path("sources/raw.yml")
    )

    assert tuple(entry.name for entry in source_entries) == test_case.expected_source_names
    assert (
        tuple(tuple(column.name for column in entry.columns) for entry in source_entries)
        == test_case.expected_column_names
    )
    assert (
        tuple(entry.type_enforcement for entry in source_entries)
        == test_case.expected_type_enforcement_values
    )


ERROR_TEST_CASES: list[ParseSourcesYamlErrorTestCase] = [
    ParseSourcesYamlErrorTestCase(
        description="raises when the file does not contain a top-level mapping",
        contents="- name: raw_orders\n",
        expected_error_fragment="must contain a top-level mapping",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when sources is not a list",
        contents="sources: {}\n",
        expected_error_fragment="sources must be a list",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when a source column entry is not a mapping",
        contents="""
        sources:
          - name: raw_orders
            columns:
              - order_id
        """,
        expected_error_fragment="source columns must contain only mappings",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_sources_yaml_when_parsing_then_it_raises_clear_errors(
    test_case: ParseSourcesYamlErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        parse_sources_yml(test_case.contents, Path("sources/raw.yml"))
