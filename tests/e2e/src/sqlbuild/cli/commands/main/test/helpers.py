"""Helpers for sqb test command e2e tests."""

from __future__ import annotations


def build_chain_test_project_files(*, sql_analysis_enabled: bool) -> dict[str, str]:
    """Build an inline project with a two-model SQL unit-test chain."""

    sql_analysis_value: str = {False: "false", True: "true"}[sql_analysis_enabled]
    return {
        "sqlbuild_project.toml": (
            'name = "demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "demo.duckdb"\n\n'
            "[settings]\n"
            f"sql_analysis = {sql_analysis_value}\n"
        ),
        "models/stg_orders.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  id,\n"
            "  @mocked_amount() AS amount,\n"
            "  @mocked_country() AS country,\n"
            "  @mocked_literal_text() AS literal_text,\n"
            "  @real_status() AS status\n"
            'FROM __source("raw")'
        ),
        "models/fact_orders.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  id,\n"
            "  amount + 1 AS adjusted,\n"
            "  country,\n"
            "  literal_text,\n"
            "  status\n"
            'FROM __ref("stg_orders")'
        ),
        "models/_macros/test_macros.py": (
            "def mocked_amount() -> str:\n"
            '    return "0"\n\n'
            "def mocked_country() -> str:\n"
            "    return \"'CA'\"\n\n"
            "def mocked_literal_text() -> str:\n"
            "    return \"'real'\"\n\n"
            "def real_status() -> str:\n"
            "    return \"'active'\"\n"
        ),
        "sources/raw.yml": "sources:\n  - name: raw\n    schema: main\n    table: raw\n",
        "tests/unit/test_chain.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__macro__mocked_amount AS (SELECT '100'),\n"
            "__macro__mocked_country AS (SELECT '''US'''),\n"
            "__macro__mocked_literal_text AS (SELECT ''' + x + '''),\n"
            "__source__raw AS (SELECT 1 AS id),\n"
            "__expected__stg_orders AS (\n"
            "  SELECT 1 AS id, 100 AS amount, 'US' AS country, ' + x + ' AS literal_text, "
            "'active' AS status\n"
            "),\n"
            "__expected__fact_orders AS (\n"
            "  SELECT 1 AS id, 101 AS adjusted, 'US' AS country, ' + x + ' AS "
            "literal_text, 'active' AS status\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_parameterized_test_project_files() -> dict[str, str]:
    """Build an inline project with two independently selectable test cases."""

    return {
        "sqlbuild_project.toml": (
            'name = "parameter_case_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "parameter_case_demo.duckdb"\n'
        ),
        "models/orders.sql": 'MODEL ();\n\nSELECT status FROM __source("raw_orders")\n',
        "models/customers.sql": ('MODEL ();\n\nSELECT status FROM __source("raw_orders")\n'),
        "sources/raw_orders.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "tests/unit/test_orders.sql": (
            'TEST (name "order_status", parameters (status string), cases ('
            'open_case (status "open"), closed_case (status "closed")));\n\n'
            "WITH\n"
            '__source__raw_orders AS (SELECT @param("status") AS status),\n'
            '__expected__orders AS (SELECT @param("status") AS status)\n'
            "SELECT 1\n"
        ),
        "tests/unit/test_customers.sql": (
            'TEST (name "customer_status", parameters (status string), '
            'cases (customer_only (status "active")));\n\n'
            "WITH\n"
            '__source__raw_orders AS (SELECT @param("status") AS status),\n'
            '__expected__customers AS (SELECT @param("status") AS status)\n'
            "SELECT 1\n"
        ),
    }


def build_mock_boundary_test_project_files() -> dict[str, str]:
    """Build a test whose ref mock intentionally replaces one real model."""

    return {
        "sqlbuild_project.toml": (
            'name = "mock_boundary_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "mock_boundary_demo.duckdb"\n'
        ),
        "models/stg_orders.sql": "MODEL ();\n\nSELECT 1 AS order_id\n",
        "models/int_orders.sql": ('MODEL ();\n\nSELECT order_id FROM __ref("stg_orders")\n'),
        "models/fact_orders.sql": ('MODEL ();\n\nSELECT order_id FROM __ref("int_orders")\n'),
        "tests/unit/test_fact_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__ref__stg_orders AS (SELECT 1 AS order_id),\n"
            "__expected__fact_orders AS (SELECT 1 AS order_id)\n"
            "SELECT 1\n"
        ),
    }


def build_unsatisfied_leaf_test_project_files() -> dict[str, str]:
    """Build a test that omits the source mock required by its real model chain."""

    files: dict[str, str] = build_chain_test_project_files(sql_analysis_enabled=True)
    files["sources/raw.yml"] = (
        "sources:\n"
        "  - name: raw\n    schema: main\n    table: raw\n"
        "  - name: unused\n    schema: main\n    table: unused\n"
    )
    files["tests/unit/test_chain.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__unused AS (SELECT 1 AS id),\n"
        "__expected__fact_orders AS (\n"
        "  SELECT 1 AS id, 101 AS adjusted, 'US' AS country, "
        "'literal' AS literal_text, 'active' AS status\n"
        ")\n"
        "SELECT 1\n"
    )
    return files


def build_missing_mock_columns_project_files() -> dict[str, str]:
    """Build a test whose source fixture omits two statically required columns."""

    return {
        "sqlbuild_project.toml": (
            'name = "missing_fixture_columns"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "missing_fixture_columns.duckdb"\n'
        ),
        "models/orders.sql": (
            'MODEL ();\n\nSELECT customer_id, status FROM __source("raw_orders")\n'
        ),
        "sources/raw_orders.yml": (
            "sources:\n"
            "  - name: raw_orders\n"
            "    schema: main\n"
            "    table: raw_orders\n"
            "    columns:\n"
            "      - name: customer_id\n"
            "      - name: status\n"
        ),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__source__raw_orders AS (SELECT 1 AS order_id),\n"
            "__expected__orders AS (SELECT 100 AS customer_id, 'open' AS status)\n"
            "SELECT 1\n"
        ),
    }


def build_partial_source_fixture_project_files() -> dict[str, str]:
    """Build a source fixture with one required nullable column omitted."""

    return {
        "sqlbuild_project.toml": (
            'name = "partial_source_fixture"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "partial_source_fixture.duckdb"\n'
        ),
        "models/orders.sql": ('MODEL ();\n\nSELECT order_id, status FROM __source("raw_orders")\n'),
        "sources/raw_orders.yml": (
            "sources:\n"
            "  - name: raw_orders\n"
            "    schema: main\n"
            "    table: raw_orders\n"
            "    columns:\n"
            "      - name: order_id\n        type: INTEGER\n        nullable: false\n"
            "      - name: status\n        type: VARCHAR\n        nullable: true\n"
        ),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__source__raw_orders AS (SELECT 1 AS order_id),\n"
            "__expected__orders AS (\n"
            "  SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_unspecified_nullability_fixture_project_files() -> dict[str, str]:
    """Build a typed partial source fixture whose nullability is unspecified."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["sources/raw_orders.yml"] = files["sources/raw_orders.yml"].replace(
        "        type: VARCHAR\n        nullable: true\n",
        "        type: VARCHAR\n",
    )
    return files


def build_partial_ref_fixture_project_files() -> dict[str, str]:
    """Build a model-ref fixture with one required nullable column omitted."""

    return {
        "sqlbuild_project.toml": (
            'name = "partial_ref_fixture"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "partial_ref_fixture.duckdb"\n'
        ),
        "models/stg_orders.sql": (
            "MODEL ();\n\nSELECT CAST(1 AS INTEGER) AS order_id, CAST(NULL AS VARCHAR) AS status\n"
        ),
        "models/orders.sql": ('MODEL ();\n\nSELECT order_id, status FROM __ref("stg_orders")\n'),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__ref__stg_orders AS (SELECT 1 AS order_id),\n"
            "__expected__orders AS (\n"
            "  SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_partial_seed_fixture_project_files() -> dict[str, str]:
    """Build a seed fixture with one required nullable column omitted."""

    return {
        "sqlbuild_project.toml": (
            'name = "partial_seed_fixture"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "partial_seed_fixture.duckdb"\n'
        ),
        "models/countries.sql": (
            'MODEL ();\n\nSELECT country_code, country_name FROM __seed("country_codes")\n'
        ),
        "seeds/country_codes.csv": "country_code,country_name\nUS,United States\n",
        "seeds/schema.yml": (
            "seeds:\n"
            "  - name: country_codes\n"
            "    columns:\n"
            "      - name: country_code\n        type: VARCHAR\n        nullable: false\n"
            "      - name: country_name\n        type: VARCHAR\n        nullable: true\n"
        ),
        "tests/unit/test_countries.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__seed__country_codes AS (SELECT 'US' AS country_code),\n"
            "__expected__countries AS (\n"
            "  SELECT 'US' AS country_code, CAST(NULL AS VARCHAR) AS country_name\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_irrelevant_omitted_column_project_files() -> dict[str, str]:
    """Build a fixture omitting a known nullable column outside the compiled closure."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["models/orders.sql"] = 'MODEL ();\n\nSELECT order_id FROM __source("raw_orders")\n'
    files["tests/unit/test_orders.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (SELECT 1 AS order_id),\n"
        "__expected__orders AS (SELECT 1 AS order_id)\n"
        "SELECT 1\n"
    )
    return files


def build_star_partial_fixture_project_files() -> dict[str, str]:
    """Build a contracted star model requiring the complete known source shape."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["sources/raw_orders.yml"] = files["sources/raw_orders.yml"].replace(
        "    columns:\n", "    contract: enforced\n    columns:\n"
    )
    files["models/orders.sql"] = 'MODEL ();\n\nSELECT * FROM __source("raw_orders")\n'
    return files


def build_empty_partial_fixture_project_files() -> dict[str, str]:
    """Build a zero-row fixture that still needs a nullable typed column."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["tests/unit/test_orders.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (SELECT 1 AS order_id WHERE FALSE),\n"
        "__expected__orders AS (\n"
        "  SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status WHERE FALSE\n"
        ")\n"
        "SELECT 1\n"
    )
    return files


def build_explicit_typed_null_fixture_project_files() -> dict[str, str]:
    """Build a complete fixture with an explicit typed null supplied by the author."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["tests/unit/test_orders.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (\n"
        "  SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status\n"
        "),\n"
        "__expected__orders AS (\n"
        "  SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status\n"
        ")\n"
        "SELECT 1\n"
    )
    return files


def build_qualified_star_other_relation_project_files() -> dict[str, str]:
    """Build a qualified star that does not target the only mocked relation."""

    return {
        "sqlbuild_project.toml": (
            'name = "qualified_star_other_relation"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "qualified_star_other_relation.duckdb"\n'
        ),
        "models/stg_orders.sql": "MODEL ();\n\nSELECT 1 AS stg_id\n",
        "models/orders.sql": (
            "MODEL ();\n\n"
            "SELECT stg.*, raw.status\n"
            'FROM __ref("stg_orders") stg\n'
            'JOIN __source("raw_orders") raw ON TRUE\n'
        ),
        "sources/raw_orders.yml": (
            "sources:\n"
            "  - name: raw_orders\n"
            "    schema: main\n"
            "    table: raw_orders\n"
            "    contract: enforced\n"
            "    columns:\n"
            "      - name: order_id\n        type: INTEGER\n        nullable: false\n"
            "      - name: status\n        type: VARCHAR\n        nullable: false\n"
            "      - name: created_at\n        type: TIMESTAMP\n        nullable: false\n"
        ),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__source__raw_orders AS (SELECT 'open' AS status),\n"
            "__expected__orders AS (SELECT 1 AS stg_id, 'open' AS status)\n"
            "SELECT 1\n"
        ),
    }


def build_mixed_case_partial_fixture_project_files() -> dict[str, str]:
    """Build a completed fixture with an as-written mixed-case unquoted alias."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["models/orders.sql"] = 'MODEL ();\n\nSELECT status, note FROM __source("raw_orders")\n'
    files["sources/raw_orders.yml"] = (
        "sources:\n"
        "  - name: raw_orders\n"
        "    schema: main\n"
        "    table: raw_orders\n"
        "    columns:\n"
        "      - name: status\n        type: VARCHAR\n        nullable: false\n"
        "      - name: note\n        type: VARCHAR\n        nullable: true\n"
    )
    files["tests/unit/test_orders.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (SELECT 'open' AS Status),\n"
        "__expected__orders AS (\n"
        "  SELECT 'open' AS status, CAST(NULL AS VARCHAR) AS note\n"
        ")\n"
        "SELECT 1\n"
    )
    return files


def build_invalid_partial_fixture_project_files(
    *, status_column_attributes: str, supplied_column: str = "order_id"
) -> dict[str, str]:
    """Build one partial source fixture that cannot be completed safely."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["sources/raw_orders.yml"] = (
        "sources:\n"
        "  - name: raw_orders\n"
        "    schema: main\n"
        "    table: raw_orders\n"
        "    contract: enforced\n"
        "    columns:\n"
        "      - name: order_id\n        type: INTEGER\n        nullable: false\n"
        "      - name: status\n"
        f"{status_column_attributes}"
    )
    files["tests/unit/test_orders.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        f"__source__raw_orders AS (SELECT 1 AS {supplied_column}),\n"
        "__expected__orders AS (SELECT 1 AS order_id, 'open' AS status)\n"
        "SELECT 1\n"
    )
    return files


def build_incompatible_fixture_type_project_files(*, adapter_name: str) -> dict[str, str]:
    """Build a test whose expected scalar conflicts with an array model column."""

    array_expression: str = {
        "duckdb": "[1, 2]",
        "snowflake": "ARRAY_CONSTRUCT(1, 2)",
    }[adapter_name]
    return {
        "sqlbuild_project.toml": (
            'name = "incompatible_fixture_type"\n'
            f'adapter = "{adapter_name}"\n\n'
            "[connection]\n"
            'database = "incompatible_fixture_type.duckdb"\n'
            'schema = "main"\n'
        ),
        "models/orders.sql": (
            'MODEL (database "fixture_db", schema "main");\n\n'
            'SELECT item_ids FROM __source("raw_orders")\n'
        ),
        "sources/raw_orders.yml": (
            "sources:\n"
            "  - name: raw_orders\n"
            "    schema: main\n"
            "    table: raw_orders\n"
            "    columns:\n"
            "      - name: item_ids\n        type: ARRAY\n"
        ),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            f"__source__raw_orders AS (SELECT {array_expression} AS item_ids),\n"
            "__expected__orders AS (SELECT '1,2' AS item_ids)\n"
            "SELECT 1\n"
        ),
    }


def build_complex_values_fixture_project_files(*, adapter_name: str) -> dict[str, str]:
    """Build a minimal complex-string VALUES fixture for one adapter dialect."""

    return {
        "sqlbuild_project.toml": (
            'name = "complex_values_fixture"\n'
            f'adapter = "{adapter_name}"\n\n'
            "[connection]\n"
            'database = "complex_values_fixture.duckdb"\n'
            'schema = "main"\n'
        ),
        "models/orders.sql": (
            'MODEL (database "fixture_db", schema "main");\n\n'
            'SELECT order_id, mapping_text FROM __source("raw_orders")\n'
        ),
        "sources/raw_orders.yml": (
            "sources:\n"
            "  - name: raw_orders\n"
            "    schema: main\n"
            "    table: raw_orders\n"
            "    columns:\n"
            "      - name: order_id\n        type: INTEGER\n"
            "      - name: mapping_text\n        type: VARCHAR\n"
        ),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__source__raw_orders AS (\n"
            "  SELECT order_id, mapping_text FROM (VALUES\n"
            "    (1, 'alpha,beta [one] (two)'),\n"
            "    (2, 'gamma(delta),[epsilon]')\n"
            ") AS fixture(order_id, mapping_text)\n"
            "),\n"
            "__expected__orders AS (\n"
            "  SELECT order_id, mapping_text FROM (VALUES\n"
            "    (1, 'alpha,beta [one] (two)'),\n"
            "    (2, 'gamma(delta),[epsilon]')\n"
            ") AS fixture(order_id, mapping_text)\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_star_mock_fixture_project_files() -> dict[str, str]:
    """Build a valid source fixture whose columns come from a star projection."""

    files: dict[str, str] = build_missing_mock_columns_project_files()
    files["tests/unit/test_orders.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (\n"
        "  SELECT * FROM (VALUES (100, 'open')) AS fixture(customer_id, status)\n"
        "),\n"
        "__expected__orders AS (SELECT 100 AS customer_id, 'open' AS status)\n"
        "SELECT 1\n"
    )
    return files


def build_transformed_collection_project_files() -> dict[str, str]:
    """Build a valid aggregation that changes a scalar input into a collection output."""

    return {
        "sqlbuild_project.toml": (
            'name = "transformed_collection"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "transformed_collection.duckdb"\n'
        ),
        "models/order_statuses.sql": (
            'MODEL ();\n\nSELECT list(status) AS statuses FROM __source("raw_orders")\n'
        ),
        "sources/raw_orders.yml": (
            "sources:\n"
            "  - name: raw_orders\n"
            "    schema: main\n"
            "    table: raw_orders\n"
            "    columns:\n"
            "      - name: status\n        type: VARCHAR\n"
        ),
        "tests/unit/test_order_statuses.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__source__raw_orders AS (SELECT 'open' AS status),\n"
            "__expected__order_statuses AS (SELECT ['open'] AS statuses)\n"
            "SELECT 1\n"
        ),
    }


def build_multiple_invalid_fixtures_project_files() -> dict[str, str]:
    """Build two invalid tests so planning must aggregate both diagnostics."""

    files: dict[str, str] = build_missing_mock_columns_project_files()
    del files["tests/unit/test_orders.sql"]
    files["tests/unit/test_orders_a.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (SELECT 'open' AS status),\n"
        "__expected__orders AS (SELECT 100 AS customer_id, 'open' AS status)\n"
        "SELECT 1\n"
    )
    files["tests/unit/test_orders_b.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (SELECT 100 AS customer_id),\n"
        "__expected__orders AS (SELECT 100 AS customer_id, 'open' AS status)\n"
        "SELECT 1\n"
    )
    return files


def build_assertion_test_project_files(*, failing: bool) -> dict[str, str]:
    """Build an inline project with a SQL unit-test zero-row assertion."""

    amount: int = {False: 10, True: -10}[failing]
    return {
        "sqlbuild_project.toml": (
            'name = "assertion_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "assertion_demo.duckdb"\n\n'
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "models/orders.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  id AS order_id,\n"
            "  amount\n"
            'FROM __source("raw_orders")\n'
        ),
        "tests/unit/orders_assert.sql": (
            "TEST();\n\n"
            "WITH\n"
            f"__source__raw_orders AS (SELECT 1 AS id, {amount} AS amount),\n"
            "__assert__no_negative_orders AS (\n"
            '  SELECT * FROM __ref("orders") WHERE amount < 0\n'
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_macro_test_project_files() -> dict[str, str]:
    """Build an inline project with a macro unit test guarding one model."""

    return {
        "sqlbuild_project.toml": (
            'name = "macro_test_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "macro_test_demo.duckdb"\n\n'
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "macros/status.py": (
            'def normalize_status(value: str) -> str:\n    return f"LOWER(TRIM({value}))"\n'
        ),
        "models/orders.sql": (
            "MODEL (materialized table);\n\nSELECT @normalize_status(\"'  PAID  '\") AS status\n"
        ),
        "tests/unit/test_normalize_status.sql": (
            'TEST (mode macro, name "normalizes_status");\n\n'
            "WITH\n"
            "input_values AS (SELECT '  PAID  ' AS raw_status),\n"
            "__macro_actual__ AS (\n"
            '  SELECT @normalize_status("raw_status") AS status FROM input_values\n'
            "),\n"
            "__macro_expected__ AS (SELECT 'paid' AS status)\n"
            "SELECT 1\n"
        ),
    }
