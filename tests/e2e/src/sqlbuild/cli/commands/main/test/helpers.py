"""Helpers for sqb test command e2e tests."""

from __future__ import annotations


def build_dynamic_pivot_test_project_files() -> dict[str, str]:
    """Build a Snowflake dynamic-pivot project for offline test-plan inspection."""

    return {
        "sqlbuild_project.toml": (
            'name = "dynamic_pivot_test_plan"\n'
            'adapter = "snowflake"\n\n'
            "[defaults]\n"
            'contract = "enforced"\n'
        ),
        "models/stg_order_amounts.sql": (
            "MODEL (\n"
            "  database analytics,\n"
            "  schema staging,\n"
            "  columns (\n"
            "    customer_id (type INTEGER),\n"
            "    category (type VARCHAR),\n"
            '    amount (type "DECIMAL(12,2)"),\n'
            "    country (type VARCHAR),\n"
            "  ),\n"
            ");\n"
            "SELECT CAST(1 AS INTEGER) AS customer_id, "
            "CAST('books' AS VARCHAR) AS category, "
            "CAST(10.25 AS DECIMAL(12,2)) AS amount, "
            "CAST('US' AS VARCHAR) AS country\n"
        ),
        "models/customer_category_amounts.sql": (
            "MODEL (\n"
            "  database analytics,\n"
            "  schema mart,\n"
            "  columns (\n"
            "    customer_id (type INTEGER),\n"
            "    country (type VARCHAR),\n"
            "  ),\n"
            "  dynamic_columns (\n"
            "    category_amounts (\n"
            "      pivot_column category,\n"
            "      value_column amount,\n"
            "      aggregate MAX,\n"
            '      type "DECIMAL(12,2)"\n'
            "    )\n"
            "  ),\n"
            ");\n"
            "WITH pivot_input AS (\n"
            "  SELECT customer_id, category, amount, country\n"
            '  FROM __ref("stg_order_amounts")\n'
            "), final AS (\n"
            "  SELECT *\n"
            "  FROM pivot_input PIVOT(MAX(amount) FOR category IN (ANY ORDER BY category))\n"
            ")\n"
            "SELECT * FROM final\n"
        ),
        "tests/unit/test_customer_category_amounts.sql": (
            'TEST (name "customer_category_amounts__empty_input");\n\n'
            "WITH __ref__stg_order_amounts AS (\n"
            "  SELECT\n"
            "    CAST(NULL AS INTEGER) AS customer_id,\n"
            "    CAST(NULL AS VARCHAR) AS category,\n"
            "    CAST(NULL AS DECIMAL(12,2)) AS amount,\n"
            "    CAST(NULL AS VARCHAR) AS country\n"
            "  WHERE FALSE\n"
            "), __assert__empty AS (\n"
            '  SELECT 1 AS unexpected_row FROM __ref("customer_category_amounts")\n'
            ")\n"
            "SELECT 1\n"
        ),
    }


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


def build_table_function_fixture_project_files() -> dict[str, str]:
    """Build a model test whose table function is replaced by a relation fixture."""

    return {
        "sqlbuild_project.toml": (
            'name = "table_function_fixture_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "table_function_fixture_demo.duckdb"\n'
        ),
        "functions/sql/customer_orders.sql": (
            "FUNCTION (\n"
            "  arguments (customer_id INTEGER),\n"
            "  returns table (order_id INTEGER)\n"
            ");\n\n"
            "SELECT customer_id * 100 AS order_id\n"
        ),
        "models/orders.sql": (
            "MODEL (columns (order_id (type INTEGER)));\n\n"
            'SELECT order_id FROM __table_fn("customer_orders")(7)\n'
        ),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "fixture_rows AS (SELECT 7 AS order_id),\n"
            "__table_fn__customer_orders AS (SELECT order_id FROM fixture_rows),\n"
            "__expected__orders AS (SELECT 7 AS order_id)\n"
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


MOCKED_UNSATISFIED_LEAF_TEST_SQL: str = (
    "TEST();\n\n"
    "WITH\n"
    "__source__raw AS (SELECT 1 AS id),\n"
    "__expected__fact_orders AS (\n"
    "  SELECT 1 AS id, 1 AS adjusted, 'CA' AS country, "
    "'real' AS literal_text, 'active' AS status\n"
    ")\n"
    "SELECT 1\n"
)


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


def build_open_schema_ref_fixture_project_files() -> dict[str, str]:
    """Build a fixture with a required column beyond a partial star-model contract."""

    return {
        "sqlbuild_project.toml": (
            'name = "open_schema_ref_fixture"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "open_schema_ref_fixture.duckdb"\n'
        ),
        "models/stg_orders.sql": (
            "MODEL (\n"
            "  contract enforced,\n"
            "  columns (\n"
            "    order_id (type INTEGER),\n"
            "  ),\n"
            ");\n\n"
            'SELECT * FROM __source("raw_orders")\n'
        ),
        "models/orders.sql": ('MODEL ();\n\nSELECT order_id, status FROM __ref("stg_orders")\n'),
        "sources/raw_orders.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__ref__stg_orders AS (SELECT 1 AS order_id, 'open' AS status),\n"
            "__expected__orders AS (SELECT 1 AS order_id, 'open' AS status)\n"
            "SELECT 1\n"
        ),
    }


def build_recursive_ref_fixture_project_files() -> dict[str, str]:
    """Build a fixture for a recursive model with derived output columns."""

    return {
        "sqlbuild_project.toml": (
            'name = "recursive_ref_fixture"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "recursive_ref_fixture.duckdb"\n'
        ),
        "models/stg_order_links.sql": (
            "MODEL (\n"
            "  contract enforced,\n"
            "  columns (\n"
            "    order_id (type INTEGER),\n"
            "    parent_order_id (type INTEGER),\n"
            "  ),\n"
            ");\n\n"
            'SELECT order_id, parent_order_id FROM __source("raw_order_links")\n'
        ),
        "models/order_roots.sql": (
            "MODEL (\n"
            "  contract enforced,\n"
            "  columns (\n"
            "    order_id (type INTEGER),\n"
            "    root_order_id (type INTEGER),\n"
            "    link_depth (type INTEGER),\n"
            "  ),\n"
            ");\n\n"
            "WITH RECURSIVE links AS (\n"
            '  SELECT * FROM __ref("stg_order_links")\n'
            "), order_chain AS (\n"
            "  SELECT order_id, order_id AS root_order_id, 0 AS link_depth\n"
            "  FROM links\n"
            "  WHERE parent_order_id IS NULL\n"
            "  UNION ALL\n"
            "  SELECT child.order_id, parent.root_order_id, parent.link_depth + 1 AS link_depth\n"
            "  FROM links AS child\n"
            "  INNER JOIN order_chain AS parent ON child.parent_order_id = parent.order_id\n"
            ")\n"
            "SELECT order_id, root_order_id, link_depth FROM order_chain\n"
        ),
        "sources/raw_order_links.yml": (
            "sources:\n"
            "  - name: raw_order_links\n"
            "    schema: main\n"
            "    table: raw_order_links\n"
            "    columns:\n"
            "      - name: order_id\n        type: INTEGER\n"
            "      - name: parent_order_id\n        type: INTEGER\n"
        ),
        "tests/unit/test_order_roots.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__ref__stg_order_links AS (\n"
            "  SELECT 1 AS order_id, CAST(NULL AS INTEGER) AS parent_order_id\n"
            "),\n"
            "__expected__order_roots AS (\n"
            "  SELECT 1 AS order_id, 1 AS root_order_id, 0 AS link_depth\n"
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


def build_cte_partial_source_fixture_project_files() -> dict[str, str]:
    """Build a partial source fixture read through an import CTE."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["models/orders.sql"] = (
        "MODEL ();\n\n"
        "WITH staged AS (\n"
        '  SELECT order_id, status FROM __source("raw_orders")\n'
        ")\n"
        "SELECT order_id, status FROM staged\n"
    )
    return files


def build_clause_partial_source_fixture_project_files() -> dict[str, str]:
    """Build a partial source fixture whose omitted column is read only by a filter."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["models/orders.sql"] = (
        'MODEL ();\n\nSELECT order_id FROM __source("raw_orders") WHERE status IS NULL\n'
    )
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


def build_untyped_null_fixture_project_files() -> dict[str, str]:
    """Build a complete empty fixture whose bare null needs its contract type."""

    return {
        "sqlbuild_project.toml": (
            'name = "untyped_null_fixture"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "untyped_null_fixture.duckdb"\n'
        ),
        "models/orders.sql": (
            "MODEL (\n"
            "  contract enforced,\n"
            "  columns (order_year (type BIGINT)),\n"
            ");\n\n"
            "SELECT EXTRACT(YEAR FROM ordered_at) AS order_year\n"
            'FROM __source("raw_orders")\n'
        ),
        "sources/raw_orders.yml": (
            "sources:\n"
            "  - name: raw_orders\n"
            "    schema: main\n"
            "    table: raw_orders\n"
            "    contract: enforced\n"
            "    columns:\n"
            "      - name: ordered_at\n        type: DATE\n        nullable: true\n"
        ),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__source__raw_orders AS (SELECT NULL AS ordered_at WHERE FALSE),\n"
            "__expected__orders AS (\n"
            "  SELECT NULL AS order_year WHERE FALSE\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_contract_empty_fixture_project_files() -> dict[str, str]:
    """Build empty input and expected fixtures whose shapes come from contracts."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["models/orders.sql"] = (
        "MODEL (\n"
        "  contract enforced,\n"
        "  columns (\n"
        "    order_id (type INTEGER),\n"
        "    status (type VARCHAR),\n"
        "  ),\n"
        ");\n\n"
        'SELECT order_id, status FROM __source("raw_orders")\n'
    )
    files["sources/raw_orders.yml"] = files["sources/raw_orders.yml"].replace(
        "    table: raw_orders\n",
        "    table: raw_orders\n    contract: enforced\n",
    )
    files["tests/unit/test_orders.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (SELECT * FROM __empty_fixture()),\n"
        "__expected__orders AS (SELECT * FROM __empty_fixture())\n"
        "SELECT 1\n"
    )
    return files


def build_open_source_empty_fixture_project_files() -> dict[str, str]:
    """Build an empty source fixture without an authoritative source shape."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["tests/unit/test_orders.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (SELECT * FROM __empty_fixture()),\n"
        "__expected__orders AS (\n"
        "  SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status\n"
        ")\n"
        "SELECT 1\n"
    )
    return files


def build_open_expected_empty_fixture_project_files() -> dict[str, str]:
    """Build an empty expected fixture without an authoritative model shape."""

    files: dict[str, str] = build_partial_source_fixture_project_files()
    files["models/orders.sql"] = 'MODEL ();\n\nSELECT * FROM __source("raw_orders")\n'
    files["tests/unit/test_orders.sql"] = (
        "TEST();\n\n"
        "WITH\n"
        "__source__raw_orders AS (\n"
        "  SELECT 1 AS order_id, CAST(NULL AS VARCHAR) AS status\n"
        "),\n"
        "__expected__orders AS (SELECT * FROM __empty_fixture())\n"
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


def build_cte_derived_output_fixture_project_files() -> dict[str, str]:
    """Build a fixture where CTE outputs are derived from fewer source columns."""

    return {
        "sqlbuild_project.toml": (
            'name = "cte_derived_output_fixture"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "cte_derived_output_fixture.duckdb"\n'
        ),
        "models/orders.sql": (
            "MODEL ();\n\n"
            "WITH raw_orders AS (\n"
            '  SELECT * FROM __source("raw_orders")\n'
            "), derived AS (\n"
            "  SELECT\n"
            "    order_id,\n"
            "    UPPER(payload) AS normalized_status,\n"
            "    CURRENT_TIMESTAMP AS loaded_at\n"
            "  FROM raw_orders\n"
            "), final AS (\n"
            "  SELECT order_id, normalized_status, loaded_at FROM derived\n"
            ")\n"
            "SELECT order_id, normalized_status, loaded_at FROM final\n"
        ),
        "sources/raw_orders.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "tests/unit/test_orders.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__source__raw_orders AS (SELECT 1 AS order_id, 'ready' AS payload),\n"
            "__assert__orders AS (\n"
            "  SELECT 1 FROM __ref(\"orders\") WHERE normalized_status <> 'READY'\n"
            ")\n"
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


def build_diamond_chain_test_project_files(*, sql_analysis_enabled: bool) -> dict[str, str]:
    """Build a shared (diamond) upstream graph with one passing and one failing chain test."""

    sql_analysis_value: str = {False: "false", True: "true"}[sql_analysis_enabled]
    return {
        "sqlbuild_project.toml": (
            'name = "diamond_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "diamond_demo.duckdb"\n\n'
            "[settings]\n"
            f"sql_analysis = {sql_analysis_value}\n\n"
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "models/stg_orders.sql": (
            "MODEL (materialized table);\n\n"
            'SELECT id AS order_id, customer_id, amount FROM __source("raw_orders")\n'
        ),
        "models/large_orders.sql": (
            "MODEL (materialized table);\n\n"
            'SELECT order_id, customer_id, amount FROM __ref("stg_orders") WHERE amount >= 10\n'
        ),
        "models/small_orders.sql": (
            "MODEL (materialized table);\n\n"
            "WITH picked AS (\n"
            '  SELECT order_id, customer_id, amount FROM __ref("stg_orders") WHERE amount < 10\n'
            ")\n"
            "SELECT * FROM picked -- small orders only\n"
        ),
        "models/customer_order_mix.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT customer_id,\n"
            '  (SELECT COUNT(*) FROM __ref("large_orders") AS l\n'
            "    WHERE l.customer_id = c.customer_id) AS large_count,\n"
            '  (SELECT COUNT(*) FROM __ref("small_orders") AS s\n'
            "    WHERE s.customer_id = c.customer_id) AS small_count\n"
            'FROM (SELECT DISTINCT customer_id FROM __ref("stg_orders")) AS c\n'
        ),
        "tests/unit/test_customer_order_mix.sql": (
            'TEST (name "customer_order_mix_matches");\n\n'
            "WITH\n"
            "__source__raw_orders AS (\n"
            "  SELECT 1 AS id, 1 AS customer_id, 5 AS amount\n"
            "  UNION ALL SELECT 2 AS id, 1 AS customer_id, 20 AS amount\n"
            "  UNION ALL SELECT 3 AS id, 2 AS customer_id, 30 AS amount\n"
            "),\n"
            "__expected__customer_order_mix AS (\n"
            "  SELECT 1 AS customer_id, 1 AS large_count, 1 AS small_count\n"
            "  UNION ALL SELECT 2 AS customer_id, 1 AS large_count, 0 AS small_count\n"
            "),\n"
            "__assert__no_negative_large_orders AS (\n"
            '  SELECT * FROM __ref("large_orders") WHERE amount < 0\n'
            ")\n"
            "SELECT 1\n"
        ),
        "tests/unit/test_customer_order_mix_wrong.sql": (
            'TEST (name "customer_order_mix_wrong");\n\n'
            "WITH\n"
            "__source__raw_orders AS (SELECT 1 AS id, 1 AS customer_id, 5 AS amount),\n"
            "__expected__customer_order_mix AS (\n"
            "  SELECT 1 AS customer_id, 3 AS large_count, 1 AS small_count\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_deep_shared_missing_mock_project_files(*, layers: int) -> dict[str, str]:
    """Build a deep diamond graph whose test omits one source mock reached on every path."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": (
            'name = "deep_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "deep_demo.duckdb"\n\n'
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "sources/raw.yml": (
            "sources:\n"
            "  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            "  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
        ),
        "models/orders_00_left.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT o.order_id, o.amount\n"
            'FROM __source("raw_orders") AS o\n'
            'JOIN __source("raw_customers") AS c ON c.customer_id = o.customer_id\n'
        ),
        "models/orders_00_right.sql": (
            'MODEL (materialized table);\n\nSELECT order_id, amount FROM __ref("orders_00_left")\n'
        ),
    }
    for layer in range(1, layers + 1):
        previous_left: str = f"orders_{layer - 1:02d}_left"
        previous_right: str = f"orders_{layer - 1:02d}_right"
        for side in ("left", "right"):
            files[f"models/orders_{layer:02d}_{side}.sql"] = (
                "MODEL (materialized table);\n\n"
                "SELECT a.order_id, a.amount + b.amount AS amount\n"
                f'FROM __ref("{previous_left}") AS a\n'
                f'JOIN __ref("{previous_right}") AS b ON a.order_id = b.order_id\n'
            )
    files["tests/unit/test_deep_orders.sql"] = (
        'TEST (name "deep_orders_missing_mock");\n\n'
        "WITH\n"
        "__source__raw_customers AS (SELECT 1 AS customer_id),\n"
        f"__expected__orders_{layers:02d}_left AS (SELECT 1 AS order_id, 1 AS amount)\n"
        "SELECT 1\n"
    )
    return files


def build_expected_column_subset_project_files(
    *, expected_tests: dict[str, str], sql_analysis_enabled: bool = True
) -> dict[str, str]:
    """Build an orders model whose SQL tests list a chosen subset of its output columns."""

    sql_analysis_value: str = {False: "false", True: "true"}[sql_analysis_enabled]
    files: dict[str, str] = {
        "sqlbuild_project.toml": (
            'name = "expected_columns_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "expected_columns_demo.duckdb"\n\n'
            "[settings]\n"
            f"sql_analysis = {sql_analysis_value}\n\n"
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "models/orders.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT id AS order_id, customer_id, status, amount * 2 AS amount\n"
            'FROM __source("raw_orders")\n'
        ),
    }
    for test_name, expected_sql in expected_tests.items():
        files[f"tests/unit/{test_name}.sql"] = (
            f'TEST (name "{test_name}");\n\n'
            "WITH\n"
            "__source__raw_orders AS (\n"
            "  SELECT 1 AS id, 100 AS customer_id, 'paid' AS status, 5 AS amount\n"
            "  UNION ALL SELECT 2 AS id, 200 AS customer_id, 'open' AS status, 7 AS amount\n"
            "),\n"
            f"__expected__orders AS (\n  {expected_sql}\n)\n"
            "SELECT 1\n"
        )
    return files
