"""Unit tests for locating named entries in authored YAML declaration files."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.discovery.main._yaml_entry_line import yaml_entry_line
from tests.unit.src.sqlbuild.compiler.discovery.main._test_types import YamlEntryLineTestCase

_SOURCES: str = (
    "sources:\n"
    "  - name: raw_orders\n"
    "    columns:\n"
    "      - name: raw_refunds\n"
    '  - name: "raw_refunds"  # refunds feed\n'
    "  - name: 'raw_customers'\n"
    "  -   name:raw_products # products\n"
    "  - name: raw_orders\n"
)


@pytest.mark.parametrize(
    "test_case",
    (
        YamlEntryLineTestCase("plain entry", _SOURCES, "raw_orders", 2),
        YamlEntryLineTestCase(
            "outermost wins over earlier nested column", _SOURCES, "raw_refunds", 5
        ),
        YamlEntryLineTestCase("single quoted entry", _SOURCES, "raw_customers", 6),
        YamlEntryLineTestCase("compact entry with trailing comment", _SOURCES, "raw_products", 7),
        YamlEntryLineTestCase("comment text is not a name", _SOURCES, "products", None),
        YamlEntryLineTestCase(
            "unquoted line also matches its comment", _SOURCES, "raw_products # products", 7
        ),
        YamlEntryLineTestCase("missing entry", _SOURCES, "raw_shipments", None),
        YamlEntryLineTestCase("mismatched quotes", "- name: \"raw_orders'\n", "raw_orders", None),
    ),
    ids=lambda case: case.description,
)
def test_given_yaml_declarations_when_locating_entry_then_returns_outermost_line(
    test_case: YamlEntryLineTestCase,
) -> None:
    assert yaml_entry_line(contents=test_case.contents, name=test_case.name) == (
        test_case.expected_line
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
