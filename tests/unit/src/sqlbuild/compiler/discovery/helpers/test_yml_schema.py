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
        description="parses seed metadata while model metadata is header-owned",
        contents="""
        seeds:
          - name: country_codes
            columns:
              - name: country_code
                type: VARCHAR
              - name: country_name
                type: VARCHAR
        """,
        expected_model_names=(),
        expected_seed_names=("country_codes",),
        expected_model_column_names=(),
        expected_seed_column_names=(("country_code", "country_name"),),
        expected_model_audit_names=(),
        expected_column_audit_names=(),
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
        description="raises when schema yml declares model metadata",
        contents="""
        models:
          - name: stg_orders
        """,
        expected_error_fragment="model metadata must live in the model file MODEL",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when seeds is not a list",
        contents="seeds: {}\n",
        expected_error_fragment="seeds must be a list",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when a seed entry is not a mapping",
        contents="""
        seeds:
          - country_codes
        """,
        expected_error_fragment="seeds must contain only mappings",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when a seed omits columns",
        contents="""
        seeds:
          - name: country_codes
        """,
        expected_error_fragment="seed must declare at least one column",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when seed meta is not a mapping",
        contents="""
        seeds:
          - name: country_codes
            meta: nope
            columns:
              - name: country_code
                type: VARCHAR
        """,
        expected_error_fragment="seed 'meta' must be a mapping",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when seed columns is not a list",
        contents="""
        seeds:
          - name: country_codes
            columns: {}
        """,
        expected_error_fragment="seed columns must be a list",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when seed column entry is not a mapping",
        contents="""
        seeds:
          - name: country_codes
            columns:
              - country_code
        """,
        expected_error_fragment="seed columns must contain only mappings",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when a seed column omits type",
        contents="""
        seeds:
          - name: country_codes
            columns:
              - name: country_code
        """,
        expected_error_fragment="seed column 'country_code' must define non-empty string 'type'",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when seed column name is blank",
        contents="""
        seeds:
          - name: country_codes
            columns:
              - name: ""
                type: VARCHAR
        """,
        expected_error_fragment="seed column must define non-empty string 'name'",
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
