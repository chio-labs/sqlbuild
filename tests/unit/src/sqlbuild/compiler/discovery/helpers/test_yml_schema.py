from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.yml_schema import parse_schema_yml
from sqlbuild.spec.models.schema import SchemaModelEntry, SchemaSeedEntry
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    ParseSchemaYamlErrorTestCase,
    ParseSchemaYamlTestCase,
)

TEST_CASES: list[ParseSchemaYamlTestCase] = [
    ParseSchemaYamlTestCase(
        description="parses model and seed metadata with attached audits",
        contents="""
        models:
          - name: stg_orders
            description: Cleaned orders.
            type_enforcement: true
            meta:
              owner: finance
            columns:
              - name: order_id
                type: VARCHAR
                audits:
                  - not_null
                  - unique:
                      severity: warning
              - name: status
                type: VARCHAR
            audits:
              - expression_is_true:
                  name: orders valid
                  expression: "status != 'bad'"

        seeds:
          - name: country_codes
            columns:
              - name: country_code
                type: VARCHAR
              - name: country_name
                type: VARCHAR
        """,
        expected_model_names=("stg_orders",),
        expected_seed_names=("country_codes",),
        expected_model_column_names=(("order_id", "status"),),
        expected_seed_column_names=(("country_code", "country_name"),),
        expected_model_audit_names=(("expression_is_true",),),
        expected_column_audit_names=((("not_null", "unique"), ()),),
    ),
    ParseSchemaYamlTestCase(
        description="allows empty schema files with no models or seeds",
        contents="{}\n",
        expected_model_names=(),
        expected_seed_names=(),
        expected_model_column_names=(),
        expected_seed_column_names=(),
        expected_model_audit_names=(),
        expected_column_audit_names=(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_schema_yaml_variants_when_parsing_then_it_returns_expected_raw_metadata(
    test_case: ParseSchemaYamlTestCase,
) -> None:
    model_entries: tuple[SchemaModelEntry, ...]
    seed_entries: tuple[SchemaSeedEntry, ...]
    model_entries, seed_entries = parse_schema_yml(test_case.contents, Path("models/schema.yml"))

    assert tuple(entry.name for entry in model_entries) == test_case.expected_model_names
    assert tuple(entry.name for entry in seed_entries) == test_case.expected_seed_names
    assert (
        tuple(tuple(column.name for column in entry.columns) for entry in model_entries)
        == test_case.expected_model_column_names
    )
    assert (
        tuple(tuple(column.name for column in entry.columns) for entry in seed_entries)
        == test_case.expected_seed_column_names
    )
    assert (
        tuple(tuple(audit.definition_name for audit in entry.audits) for entry in model_entries)
        == test_case.expected_model_audit_names
    )
    assert (
        tuple(
            tuple(
                tuple(audit.definition_name for audit in column.audits) for column in entry.columns
            )
            for entry in model_entries
        )
        == test_case.expected_column_audit_names
    )


ERROR_TEST_CASES: list[ParseSchemaYamlErrorTestCase] = [
    ParseSchemaYamlErrorTestCase(
        description="raises when the file does not contain a top-level mapping",
        contents="- name: stg_orders\n",
        expected_error_fragment="must contain a top-level mapping",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when models is not a list",
        contents="models: {}\n",
        expected_error_fragment="models must be a list",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when an audit entry is not a string or single-key mapping",
        contents="""
        models:
          - name: stg_orders
            audits:
              - name: broken
                severity: warning
        """,
        expected_error_fragment="audits must be strings or single-key mappings",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_schema_yaml_when_parsing_then_it_raises_clear_errors(
    test_case: ParseSchemaYamlErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        parse_schema_yml(test_case.contents, Path("models/schema.yml"))
