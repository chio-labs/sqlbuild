from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile._helpers.render.parameters import expand_test_parameters
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlTest,
    CompileProjectInputs,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, TypedSqlValueRenderer
from sqlbuild.compiler.planner._helpers.output.plan_entry import scope_overlaps
from sqlbuild.sql_values.models import SqlLogicalType, SqlValue
from sqlbuild.sql_values.types import SqlValueKind
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ParameterizedSqlTestAdapterRenderingTestCase,
    ParameterizedSqlTestCompilationErrorTestCase,
    ParameterizedSqlTestCompilationTestCase,
    ParameterizedSqlTestRenderingErrorTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import compile_project_inputs
from tests.unit.src.sqlbuild.compiler.compile._test_helpers import base_repo_files


@pytest.mark.parametrize(
    "test_case",
    [
        ParameterizedSqlTestCompilationTestCase(
            description="expands ordered typed model and macro test cases before macros",
            repo_files=base_repo_files()
            | {
                "models/orders.sql": "MODEL ();\n\nSELECT 'open' AS status\n",
                "models/customers.sql": "MODEL ();\n\nSELECT 1 AS customer_id\n",
                "sources/raw.yml": "sources:\n  - name: raw_orders\n    expression: SELECT 1 AS order_id\n",
                "seeds/schema.yml": (
                    "seeds:\n  - name: country_codes\n    columns:\n"
                    "      - name: code\n        type: VARCHAR\n"
                ),
                "seeds/country_codes.csv": "code\nGB\n",
                "constants/offset.sql": "CONSTANT (name offset, value 2);\n",
                "enums/state.sql": "ENUM (name state, members [OPEN, CLOSED]);\n",
                "functions/sql/add_one.sql": """
FUNCTION (arguments (value INTEGER), returns INTEGER);

value + 1
""".strip()
                + "\n",
                "functions/sql/by_customer.sql": """
FUNCTION (
  arguments (customer_id INTEGER),
  returns table (customer_id INTEGER)
);

SELECT customer_id
""".strip()
                + "\n",
                "macros/identity.py": (
                    "def identity(value):\n    return value\n\n"
                    "def parameterized_fixture(value):\n    return str(value)\n"
                ),
                "tests/unit/a_model_cases.sql": """
TEST (
  name "status mapping",
  parameters (
    status string,
    count integer,
    enabled boolean,
    ratio float,
    amount decimal,
    note (type string, nullable true),
  ),
  cases (
    open_case (
      status "O'Brien",
      count -7,
      enabled true,
      ratio 1.25,
      amount "2.4700",
      note null,
    ),
    closed_case (
      status "closed",
      count 8,
      enabled false,
      ratio -0.5,
      amount "3.00",
      note "kept",
    ),
  ),
);

WITH
__source__raw_orders AS (SELECT @param("count") AS order_id),
__ref__orders AS (
  SELECT
    @identity(@param("status")) AS status,
    @param("status") AS status_copy,
    @param("count") AS count,
    @parameterized_fixture(@param("count")) AS boundary_count,
    @param("enabled") AS enabled,
    @param("ratio") AS ratio,
    @param("amount") AS amount,
    @param("note") AS note,
    @param("count") + @const("offset") AS adjusted_count,
    @enum("state").OPEN AS state,
    '@param("status")' AS quoted_marker
  -- @param("status") remains a comment
),
__ref__customers AS (SELECT @param("count") AS customer_id),
__seed__country_codes AS (SELECT @param("status") AS code),
__expected__orders AS (SELECT @param("status") AS status),
__expected__customers AS (SELECT @param("count") AS customer_id),
__assert__positive_count AS (SELECT 1 WHERE @param("count") < 0)
SELECT 1
""".strip()
                + "\n",
                "tests/unit/b_macro_cases.sql": """
TEST (
  name "identity macro",
  mode macro,
  parameters (value string),
  cases (first (value "one"), second (value "two")),
);

WITH
__macro_actual__ AS (SELECT @identity(@param("value")) AS value),
__macro_expected__ AS (SELECT @param("value") AS value)
SELECT 1
""".strip()
                + "\n",
                "tests/unit/c_udf_cases.sql": """
TEST (
  name "add one udf",
  mode udf,
  parameters (value integer),
  cases (small (value 2), large (value 9)),
);

WITH
__udf_actual__ AS (SELECT __udf("add_one")(@param("value")) AS value),
__udf_expected__ AS (SELECT @param("value") + 1 AS value)
SELECT 1
""".strip()
                + "\n",
                "tests/unit/d_table_fn_cases.sql": """
TEST (
  name "by customer table function",
  mode table_fn,
  parameters (customer_id integer),
  cases (first (customer_id 11), second (customer_id 22)),
);

WITH
__table_fn_actual__ AS (
  SELECT customer_id FROM __table_fn("by_customer")(@param("customer_id"))
),
__table_fn_expected__ AS (SELECT @param("customer_id") AS customer_id)
SELECT 1
""".strip()
                + "\n",
                "tests/scenarios/status.sql": """
SCENARIO (description "ordinary scenario");

WITH
__ref__orders AS (SELECT 'open' AS status),
__expected__orders AS (SELECT 'open' AS status)
SELECT 1
""".strip()
                + "\n",
            },
            expected_names=(
                "status mapping [open_case]",
                "status mapping [closed_case]",
                "identity macro [first]",
                "identity macro [second]",
                "add one udf [small]",
                "add one udf [large]",
                "by customer table function [first]",
                "by customer table function [second]",
            ),
            expected_case_names=(
                "open_case",
                "closed_case",
                "first",
                "second",
                "small",
                "large",
                "first",
                "second",
            ),
            expected_sql_fragments=(
                (
                    "'O''Brien' AS status",
                    "'O''Brien' AS status_copy",
                    "-7 AS count",
                    "-7 AS boundary_count",
                    "TRUE AS enabled",
                    "1.25 AS ratio",
                    "2.4700 AS amount",
                    "NULL AS note",
                    "-7 + 2 AS adjusted_count",
                    "'OPEN' AS state",
                    "SELECT -7 AS order_id",
                    "SELECT 'O''Brien' AS code",
                    "SELECT 'O''Brien' AS status",
                    "SELECT -7 AS customer_id",
                    "SELECT 1 WHERE -7 < 0",
                    "'@param(\"status\")' AS quoted_marker",
                    '-- @param("status") remains a comment',
                ),
                (
                    "'closed' AS status",
                    "'closed' AS status_copy",
                    "8 AS count",
                    "FALSE AS enabled",
                    "-0.5 AS ratio",
                    "3.00 AS amount",
                    "'kept' AS note",
                    "8 + 2 AS adjusted_count",
                ),
                ("SELECT one AS value", "SELECT 'one' AS value"),
                ("SELECT two AS value", "SELECT 'two' AS value"),
                ('__udf("add_one")(2)', "SELECT 2 + 1 AS value"),
                ('__udf("add_one")(9)', "SELECT 9 + 1 AS value"),
                ('__table_fn("by_customer")(11)', "SELECT 11 AS customer_id"),
                ('__table_fn("by_customer")(22)', "SELECT 22 AS customer_id"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_parameterized_sql_tests_when_compiling_then_cases_have_typed_unique_identities(
    test_case: ParameterizedSqlTestCompilationTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)
    compile_inputs: CompileProjectInputs = compile_project_inputs(project_dir=tmp_path)
    compiled: CompiledProject = assemble_compiled_project(inputs=compile_inputs)

    assert tuple(test.name for test in compiled.sql_tests) == test_case.expected_names
    assert tuple(test.key.name for test in compiled.sql_tests) == test_case.expected_names
    assert tuple(test.case_name for test in compiled.sql_tests) == test_case.expected_case_names
    assert tuple(test.case_index for test in compiled.sql_tests) == (0, 1, 0, 1, 0, 1, 0, 1)
    assert tuple(test.parent_name for test in compiled.sql_tests) == (
        "status mapping",
        "status mapping",
        "identity macro",
        "identity macro",
        "add one udf",
        "add one udf",
        "by customer table function",
        "by customer table function",
    )
    compiled_test: CompiledSqlTest
    expected_fragments: tuple[str, ...]
    for compiled_test, expected_fragments in zip(
        compiled.sql_tests,
        test_case.expected_sql_fragments,
        strict=True,
    ):
        for fragment in expected_fragments:
            assert fragment in compiled_test.sql_body, compiled_test.sql_body
    assert tuple(value.kind.value for _name, value in compiled.sql_tests[0].parameter_values) == (
        "string",
        "integer",
        "boolean",
        "float",
        "decimal",
        "null",
    )
    original_fingerprints: tuple[str | None, ...] = tuple(
        test.case_fingerprint for test in compiled.sql_tests
    )
    assert all(original_fingerprints)
    model_test_path: Path = tmp_path / "tests/unit/a_model_cases.sql"
    model_test_path.write_text(
        model_test_path.read_text(encoding="utf-8").replace('amount "2.4700"', 'amount "2.4800"'),
        encoding="utf-8",
    )
    changed: CompiledProject = assemble_compiled_project(
        inputs=compile_project_inputs(project_dir=tmp_path)
    )
    changed_fingerprints: tuple[str | None, ...] = tuple(
        test.case_fingerprint for test in changed.sql_tests
    )
    assert changed_fingerprints[0] != original_fingerprints[0]
    assert changed_fingerprints[1:] == original_fingerprints[1:]
    model_cases: tuple[CompiledSqlTest, ...] = compiled.sql_tests[:2]
    selected_orders: frozenset[CompiledObjectKey] = frozenset(
        (
            CompiledObjectKey(
                resource_type=CompiledResourceType.MODEL,
                name="orders",
            ),
        )
    )
    assert all(
        scope_overlaps(scope_deps=test.scope_deps, selected_keys=selected_orders)
        for test in model_cases
    )
    assert tuple(test.payload.expected_model_names for test in model_cases) == (
        ("orders", "customers"),
        ("orders", "customers"),
    )
    assert tuple(scenario.name for scenario in compiled.sql_scenarios) == ("status",)
    assert compiled.sql_scenarios[0].sql_body.endswith("SELECT 1")


@pytest.mark.parametrize(
    "test_case",
    [
        ParameterizedSqlTestAdapterRenderingTestCase(
            description="BigQuery preserves decimal scale with a NUMERIC literal",
            adapter_name="bigquery",
            value=SqlValue(
                logical_type=SqlLogicalType(SqlValueKind.DECIMAL),
                value=Decimal("12.3400"),
            ),
            expected_sql="SELECT NUMERIC '12.3400'",
        ),
        ParameterizedSqlTestAdapterRenderingTestCase(
            description="SQL Server uses a Unicode string literal",
            adapter_name="sqlserver",
            value=SqlValue(
                logical_type=SqlLogicalType(SqlValueKind.STRING),
                value="O'Brien",
            ),
            expected_sql="SELECT N'O''Brien'",
        ),
        ParameterizedSqlTestAdapterRenderingTestCase(
            description="SQL Server renders true as a bit-compatible scalar",
            adapter_name="sqlserver",
            value=SqlValue(
                logical_type=SqlLogicalType(SqlValueKind.BOOLEAN),
                value=True,
            ),
            expected_sql="SELECT 1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_specific_parameter_when_expanding_then_adapter_literal_is_used(
    test_case: ParameterizedSqlTestAdapterRenderingTestCase,
) -> None:
    renderer: TypedSqlValueRenderer = {
        "bigquery": BigQueryAdapter(),
        "sqlserver": SqlServerAdapter(),
    }[test_case.adapter_name]

    rendered, used_names = expand_test_parameters(
        sql='SELECT @param("value")',
        file_path=Path("tests/unit/adapter.sql"),
        values=(("value", test_case.value),),
        value_renderer=renderer,
        test_name="adapter rendering",
        case_name="one",
    )

    assert rendered == test_case.expected_sql
    assert used_names == frozenset(("value",))


@pytest.mark.parametrize(
    "test_case",
    [
        ParameterizedSqlTestCompilationErrorTestCase(
            description="rejects declared parameters unused by the template",
            test_sql=('TEST (parameters (value string), cases (one (value "x")));\n\nSELECT 1\n'),
            expected_error_fragment="declares unused parameters: value in case 'one'",
        ),
        ParameterizedSqlTestCompilationErrorTestCase(
            description="rejects references to undeclared parameters",
            test_sql=(
                'TEST (parameters (value string), cases (one (value "x")));\n\n'
                'SELECT @param("value"), @param("other")\n'
            ),
            expected_error_fragment="case 'one'.*references undeclared parameter 'other'",
        ),
        ParameterizedSqlTestCompilationErrorTestCase(
            description="rejects malformed parameter references",
            test_sql=(
                'TEST (parameters (value string), cases (one (value "x")));\n\n'
                "SELECT @param('value')\n"
            ),
            expected_error_fragment="case 'one'.*malformed @param reference",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_parameter_references_when_compiling_then_clear_error_is_raised(
    test_case: ParameterizedSqlTestCompilationErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(
        tmp_path,
        base_repo_files() | {"tests/unit/invalid_parameters.sql": test_case.test_sql},
    )

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        compile_project_inputs(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    [
        ParameterizedSqlTestRenderingErrorTestCase(
            description="reports adapter test case and parameter when rendered value is oversized",
            rendered_value="x" * 1_000_001,
            expected_error_fragment=(
                "SQL test 'large values' case 'oversized' parameter 'value' could not be "
                "rendered by adapter 'test_adapter'"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_oversized_rendered_parameter_when_expanding_then_contextual_error_is_raised(
    test_case: ParameterizedSqlTestRenderingErrorTestCase,
) -> None:
    renderer: Mock = Mock()
    renderer.adapter_name = "test_adapter"
    renderer.render_typed_scalar.return_value = test_case.rendered_value
    value: SqlValue = SqlValue(
        logical_type=SqlLogicalType(SqlValueKind.STRING),
        value="safe",
    )

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        expand_test_parameters(
            sql='SELECT @param("value")',
            file_path=Path("tests/unit/large.sql"),
            values=(("value", value),),
            value_renderer=renderer,
            test_name="large values",
            case_name="oversized",
        )
