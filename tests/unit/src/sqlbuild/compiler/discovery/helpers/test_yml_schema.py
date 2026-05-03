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
        description="raises when a model entry is not a mapping",
        contents="""
        models:
          - stg_orders
        """,
        expected_error_fragment="models must contain only mappings",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when a model omits name",
        contents="""
        models:
          - description: no name
        """,
        expected_error_fragment="model must define non-empty string 'name'",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when model type enforcement is not a boolean",
        contents="""
        models:
          - name: stg_orders
            type_enforcement: 123
        """,
        expected_error_fragment="model 'type_enforcement' must be a boolean",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when model meta is not a mapping",
        contents="""
        models:
          - name: stg_orders
            meta: finance
        """,
        expected_error_fragment="model 'meta' must be a mapping",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when model columns is not a list",
        contents="""
        models:
          - name: stg_orders
            columns: {}
        """,
        expected_error_fragment="model columns must be a list",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when model column entry is not a mapping",
        contents="""
        models:
          - name: stg_orders
            columns:
              - order_id
        """,
        expected_error_fragment="model columns must contain only mappings",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when model column omits name",
        contents="""
        models:
          - name: stg_orders
            columns:
              - type: VARCHAR
        """,
        expected_error_fragment="model column must define non-empty string 'name'",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when model column meta is not a mapping",
        contents="""
        models:
          - name: stg_orders
            columns:
              - name: order_id
                meta: finance
        """,
        expected_error_fragment="model column 'meta' must be a mapping",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when model audits is not a list",
        contents="""
        models:
          - name: stg_orders
            audits: {}
        """,
        expected_error_fragment="model audits must be a list",
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
    ParseSchemaYamlErrorTestCase(
        description="raises when an audit entry has an empty string name",
        contents="""
        models:
          - name: stg_orders
            audits:
              - "  "
        """,
        expected_error_fragment="audits must not contain empty names",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when an audit mapping has an empty definition name",
        contents="""
        models:
          - name: stg_orders
            audits:
              - "": {}
        """,
        expected_error_fragment="audit names must be non-empty strings",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when audit arguments are not a mapping",
        contents="""
        models:
          - name: stg_orders
            audits:
              - unique: warning
        """,
        expected_error_fragment="audit 'unique' arguments must be a mapping",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when audit metadata name is not a string",
        contents="""
        models:
          - name: stg_orders
            audits:
              - unique:
                  name: 123
        """,
        expected_error_fragment="audit 'unique' 'name' must be a non-empty string",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when audit metadata description is not a string",
        contents="""
        models:
          - name: stg_orders
            audits:
              - unique:
                  description: 123
        """,
        expected_error_fragment="audit 'unique' 'description' must be a non-empty string",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when audit metadata severity is not a string",
        contents="""
        models:
          - name: stg_orders
            audits:
              - unique:
                  severity: 123
        """,
        expected_error_fragment="audit 'unique' 'severity' must be a non-empty string",
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
    ParseSchemaYamlErrorTestCase(
        description="raises when model tags is a string instead of list",
        contents="""
        models:
          - name: orders
            tags: nightly
        """,
        expected_error_fragment="model 'tags' must be a list",
    ),
    ParseSchemaYamlErrorTestCase(
        description="raises when model tags contains non-string entry",
        contents="""
        models:
          - name: orders
            tags: [123]
        """,
        expected_error_fragment="model 'tags' entries must be strings",
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
