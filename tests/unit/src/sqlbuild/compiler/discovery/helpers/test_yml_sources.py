from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.yml_sources import parse_sources_yml
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    ParseSourcesYamlErrorTestCase,
    ParseSourcesYamlTestCase,
)
from tests.unit.src.sqlbuild.compiler.discovery.helpers.helpers import expected_or_actual

TEST_CASES: list[ParseSourcesYamlTestCase] = [
    ParseSourcesYamlTestCase(
        description="parses sources with quality metadata and columns",
        contents="""
        sources:
          - name: raw_orders
            database: raw
            schema: public
            table: orders
            description: Raw orders from ingestion.
            type_enforcement: true
            meta:
              owner: finance
            audits:
              - source_freshness:
                  threshold_hours: 2
            columns:
              - name: order_id
                type: VARCHAR
                nullable: false
                description: Stable order identifier.
                audits:
                  - not_null
              - name: created_at
                type: TIMESTAMP_NTZ
                nullable: true
                audits:
                  - recency:
                      max_age_hours: 24
          - name: raw_customers
            schema: public
            table: customers
        """,
        expected_source_names=("raw_orders", "raw_customers"),
        expected_column_names=(("order_id", "created_at"), ()),
        expected_type_enforcement_values=(True, None),
        expected_expressions=(None, None),
        expected_source_audit_names=(("source_freshness",), ()),
        expected_column_audit_names=((("not_null",), ("recency",)), ()),
        expected_column_nullables=((False, True), ()),
    ),
    ParseSourcesYamlTestCase(
        description="defaults expression source type enforcement from typed columns",
        contents="""
        sources:
          - name: raw_orders
            expression: |
              SELECT 1 AS order_id, 'placed' AS status
            columns:
              - name: order_id
                type: INTEGER
              - name: status
                type: VARCHAR
        """,
        expected_source_names=("raw_orders",),
        expected_column_names=(("order_id", "status"),),
        expected_type_enforcement_values=(True,),
        expected_expressions=("SELECT 1 AS order_id, 'placed' AS status\n",),
        expected_source_audit_names=((),),
        expected_column_audit_names=(((), ()),),
    ),
    ParseSourcesYamlTestCase(
        description="allows expression source type enforcement to opt in explicitly",
        contents="""
        sources:
          - name: raw_orders
            expression: |
              SELECT 1 AS order_id, 'placed' AS status
            type_enforcement: true
            columns:
              - name: order_id
                type: INTEGER
        """,
        expected_source_names=("raw_orders",),
        expected_column_names=(("order_id",),),
        expected_type_enforcement_values=(True,),
        expected_expressions=("SELECT 1 AS order_id, 'placed' AS status\n",),
        expected_source_audit_names=((),),
        expected_column_audit_names=(((),),),
    ),
    ParseSourcesYamlTestCase(
        description="does not enforce source types for untyped column metadata",
        contents="""
        sources:
          - name: raw_orders
            schema: public
            table: orders
            columns:
              - name: order_id
                description: Stable order identifier.
        """,
        expected_source_names=("raw_orders",),
        expected_column_names=(("order_id",),),
        expected_type_enforcement_values=(None,),
        expected_expressions=(None,),
        expected_source_audit_names=((),),
        expected_column_audit_names=(((),),),
    ),
    ParseSourcesYamlTestCase(
        description="allows source columns to opt out of default type enforcement",
        contents="""
        sources:
          - name: raw_orders
            schema: public
            table: orders
            type_enforcement: false
            columns:
              - name: order_id
                type: INTEGER
        """,
        expected_source_names=("raw_orders",),
        expected_column_names=(("order_id",),),
        expected_type_enforcement_values=(False,),
        expected_expressions=(None,),
        expected_source_audit_names=((),),
        expected_column_audit_names=(((),),),
    ),
    ParseSourcesYamlTestCase(
        description="allows empty sources files with no declarations",
        contents="{}\n",
        expected_source_names=(),
        expected_column_names=(),
        expected_type_enforcement_values=(),
        expected_expressions=(),
        expected_source_audit_names=(),
        expected_column_audit_names=(),
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
    actual_column_nullables: tuple[tuple[bool | None, ...], ...] = tuple(
        tuple(column.nullable for column in entry.columns) for entry in source_entries
    )
    assert actual_column_nullables == expected_or_actual(
        test_case.expected_column_nullables, actual_column_nullables
    )
    assert (
        tuple(entry.type_enforcement for entry in source_entries)
        == test_case.expected_type_enforcement_values
    )
    assert tuple(entry.expression for entry in source_entries) == test_case.expected_expressions
    assert (
        tuple(tuple(audit.definition_name for audit in entry.audits) for entry in source_entries)
        == test_case.expected_source_audit_names
    )
    assert (
        tuple(
            tuple(
                tuple(audit.definition_name for audit in column.audits) for column in entry.columns
            )
            for entry in source_entries
        )
        == test_case.expected_column_audit_names
    )


ERROR_TEST_CASES: list[ParseSourcesYamlErrorTestCase] = [
    ParseSourcesYamlErrorTestCase(
        description="raises when the file does not contain a top-level mapping",
        contents="- name: raw_orders\n",
        expected_error_fragment="must contain a top-level mapping",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source meta is not a mapping",
        contents="""
        sources:
          - name: raw_orders
            meta: []
        """,
        expected_error_fragment="source 'meta' must be a mapping",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when sources is not a list",
        contents="sources: {}\n",
        expected_error_fragment="sources must be a list",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when one source entry is not a mapping",
        contents="""
        sources:
          - raw_orders
        """,
        expected_error_fragment="sources must contain only mappings",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when a source omits name",
        contents="""
        sources:
          - schema: public
        """,
        expected_error_fragment="source must define non-empty string 'name'",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source database is blank",
        contents="""
        sources:
          - name: raw_orders
            database: ""
        """,
        expected_error_fragment="source 'database' must be a non-empty string",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source schema is blank",
        contents="""
        sources:
          - name: raw_orders
            schema: ""
        """,
        expected_error_fragment="source 'schema' must be a non-empty string",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source table is blank",
        contents="""
        sources:
          - name: raw_orders
            table: ""
        """,
        expected_error_fragment="source 'table' must be a non-empty string",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source expression is blank",
        contents="""
        sources:
          - name: raw_orders
            expression: ""
        """,
        expected_error_fragment="source 'expression' must be a non-empty string",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source expression is mixed with relation fields",
        contents="""
        sources:
          - name: raw_orders
            schema: main
            expression: SELECT 1 AS order_id
        """,
        expected_error_fragment="source 'raw_orders' cannot define expression with schema",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when expression source enforces types without typed columns",
        contents="""
        sources:
          - name: raw_orders
            expression: SELECT 1 AS order_id
            type_enforcement: true
        """,
        expected_error_fragment=(
            "source 'raw_orders' uses expression with type_enforcement but has no typed columns"
        ),
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source type enforcement is not a boolean",
        contents="""
        sources:
          - name: raw_orders
            type_enforcement: 123
        """,
        expected_error_fragment="source 'type_enforcement' must be a boolean",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source audits is not a list",
        contents="""
        sources:
          - name: raw_orders
            audits: {}
        """,
        expected_error_fragment="source audits must be a list",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source columns is not a list",
        contents="""
        sources:
          - name: raw_orders
            columns: {}
        """,
        expected_error_fragment="source columns must be a list",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source column meta is not a mapping",
        contents="""
        sources:
          - name: raw_orders
            columns:
              - name: order_id
                meta: []
        """,
        expected_error_fragment="source column 'meta' must be a mapping",
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
    ParseSourcesYamlErrorTestCase(
        description="raises when source column omits name",
        contents="""
        sources:
          - name: raw_orders
            columns:
              - type: VARCHAR
        """,
        expected_error_fragment="source column must define non-empty string 'name'",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source column audits is not a list",
        contents="""
        sources:
          - name: raw_orders
            columns:
              - name: order_id
                audits: {}
        """,
        expected_error_fragment="source column audits must be a list",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source column nullable is not a boolean",
        contents="""
        sources:
          - name: raw_orders
            columns:
              - name: order_id
                nullable: 123
        """,
        expected_error_fragment="source column 'nullable' must be a boolean",
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source column allows nulls and uses not null audit",
        contents="""
        sources:
          - name: raw_orders
            columns:
              - name: order_id
                nullable: true
                audits:
                  - not_null
        """,
        expected_error_fragment=("column 'order_id' cannot set nullable = true and audit not_null"),
    ),
    ParseSourcesYamlErrorTestCase(
        description="raises when source column type is blank",
        contents="""
        sources:
          - name: raw_orders
            columns:
              - name: order_id
                type: ""
        """,
        expected_error_fragment="source column 'type' must be a non-empty string",
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
