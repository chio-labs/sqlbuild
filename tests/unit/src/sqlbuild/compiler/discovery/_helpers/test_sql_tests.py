from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.native.sql_test_files import discover_native_test_files
from sqlbuild.compiler.discovery.exceptions import SqlTestParseError
from sqlbuild.compiler.discovery.main.omitted_ceremonial_select import (
    omitted_ceremonial_select_offset,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestCase,
    DiscoveredSqlTestFile,
    DiscoveryFileFault,
    SqlTestParameterDeclaration,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.unit.src.sqlbuild.compiler.discovery._helpers._test_types import (
    ExpectedCountTestCase,
    OmittedSelectPerformanceTestCase,
    ParseSqlTestCursorWindowTestCase,
    ParseSqlTestFileErrorTestCase,
    ParseSqlTestFileTestCase,
    ParseSqlTestModeTestCase,
)
from tests.unit.src.sqlbuild.compiler.discovery._helpers.helpers import (
    discovered_test_case_values,
    discovered_test_cases,
    discovered_test_parameters,
)
from tests.unit.src.sqlbuild.compiler.discovery.helpers import parse_sql_test_file

_FIXTURE_ROW: str = (
    "  SELECT 1 AS order_id, 'it''s (open)' AS note, \"Qty\" AS qty -- row (comment)\n  UNION ALL\n"
)


@pytest.mark.parametrize(
    "test_case",
    (
        OmittedSelectPerformanceTestCase(
            description="authored select one takes the constant-time path",
            trailing_sql="SELECT 1\n",
            fixture_rows=12_000,
            expected_offset_found=False,
            expected_max_seconds=0.05,
        ),
        OmittedSelectPerformanceTestCase(
            description="omitted select one scans a megabyte body within budget",
            trailing_sql="",
            fixture_rows=12_000,
            expected_offset_found=True,
            expected_max_seconds=1.0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_large_fixture_body_when_locating_omitted_select_then_completes_within_budget(
    test_case: OmittedSelectPerformanceTestCase,
) -> None:
    sql: str = (
        "WITH __source__orders AS (\n"
        + _FIXTURE_ROW * test_case.fixture_rows
        + "  SELECT 2 AS order_id, 'x' AS note, 3 AS qty\n),\n"
        + "__expected__orders AS (SELECT 1 AS order_id)\n"
        + test_case.trailing_sql
    )
    timings: list[float] = []
    offset: int | None = None

    for _ in range(3):
        started: float = time.perf_counter()
        offset = omitted_ceremonial_select_offset(sql=sql, syntax=SqlLexicalSyntax())
        timings.append(time.perf_counter() - started)

    assert (offset is not None) == test_case.expected_offset_found
    assert min(timings) < test_case.expected_max_seconds


@pytest.mark.parametrize(
    "test_case",
    (ExpectedCountTestCase(description="one invalid file reports one fault", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_invalid_test_file_when_discovering_tolerantly_then_reports_file_fault(
    tmp_path: Path,
    test_case: ExpectedCountTestCase,
) -> None:
    tests_dir: Path = tmp_path / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "a_invalid.sql").write_text("SELECT 1", encoding="utf-8")
    (tests_dir / "b_valid.sql").write_text('TEST (name "valid_order");\nSELECT 1', encoding="utf-8")
    faults: list[DiscoveryFileFault] = []

    discovered: tuple[DiscoveredSqlTestFile, ...] = discover_native_test_files(
        project_dir=tmp_path,
        on_fault=faults.append,
    )

    assert len(faults) == test_case.expected_count
    assert faults[0].path == Path("tests/unit/a_invalid.sql")
    discovered_names: list[str | None] = []
    for discovered_file in discovered:
        discovered_names.extend(block.name for block in discovered_file.blocks)
    assert tuple(discovered_names) == ("valid_order",)


@pytest.mark.parametrize(
    "test_case",
    [
        ParseSqlTestFileTestCase(
            description="discovers one unnamed test block",
            contents="""
        TEST ();

        WITH
        __source__orders AS (
          SELECT 1 AS order_id
        )
        SELECT 1
        """,
            expected_names=(None,),
            expected_sql_bodies=(
                "WITH\n__source__orders AS (\n  SELECT 1 AS order_id\n)\nSELECT 1",
            ),
            expected_test_indexes=(1,),
            expected_header_values=({},),
        ),
        ParseSqlTestFileTestCase(
            description="discovers multiple named test blocks from one file",
            contents="""
        TEST (name "first");

        WITH
        __source__orders AS (
          SELECT 1 AS order_id
        )
        SELECT 1;

        TEST (name "second");

        WITH
        __ref__orders AS (
          SELECT 2 AS order_id
        )
        SELECT 1
        """,
            expected_names=("first", "second"),
            expected_sql_bodies=(
                "WITH\n__source__orders AS (\n  SELECT 1 AS order_id\n)\nSELECT 1;",
                "WITH\n__ref__orders AS (\n  SELECT 2 AS order_id\n)\nSELECT 1",
            ),
            expected_test_indexes=(1, 2),
            expected_header_values=({"name": "first"}, {"name": "second"}),
        ),
        ParseSqlTestFileTestCase(
            description="parses a single named test block",
            contents="""
        TEST (name "orders logic", mode macro);

        SELECT 1
        """,
            expected_names=("orders logic",),
            expected_sql_bodies=("SELECT 1",),
            expected_test_indexes=(1,),
            expected_header_values=({"name": "orders logic", "mode": "macro"},),
        ),
        ParseSqlTestFileTestCase(
            description="parses typed ordered cases with nullable values",
            contents="""
        TEST (
          name "typed values",
          parameters (
            text_value string,
            integer_value integer,
            boolean_value boolean,
            float_value float,
            decimal_value decimal,
            optional_value (type string, nullable true),
          ),
          cases (
            first (
              text_value "O\\'Brien",
              integer_value -7,
              boolean_value true,
              float_value 1.25,
              decimal_value "2.4700",
              optional_value null,
            ),
            second (
              text_value "open",
              integer_value 8,
              boolean_value false,
              float_value -0.5,
              decimal_value "3.00",
              optional_value "present",
            ),
          ),
        );

        SELECT @param("text_value")
        """,
            expected_names=("typed values",),
            expected_sql_bodies=('SELECT @param("text_value")',),
            expected_test_indexes=(1,),
            expected_header_values=(
                {
                    "name": "typed values",
                    "parameters": {
                        "text_value": "string",
                        "integer_value": "integer",
                        "boolean_value": "boolean",
                        "float_value": "float",
                        "decimal_value": "decimal",
                        "optional_value": {"type": "string", "nullable": True},
                    },
                    "cases": {
                        "first": {
                            "text_value": "O'Brien",
                            "integer_value": -7,
                            "boolean_value": True,
                            "float_value": 1.25,
                            "decimal_value": "2.4700",
                            "optional_value": None,
                        },
                        "second": {
                            "text_value": "open",
                            "integer_value": 8,
                            "boolean_value": False,
                            "float_value": -0.5,
                            "decimal_value": "3.00",
                            "optional_value": "present",
                        },
                    },
                },
            ),
            expected_parameter_types=(
                "string",
                "integer",
                "boolean",
                "float",
                "decimal",
                "string",
            ),
            expected_parameter_nullability=(False, False, False, False, False, True),
            expected_case_names=("first", "second"),
            expected_case_values=(
                ("O'Brien", -7, True, 1.25, Decimal("2.4700"), None),
                ("open", 8, False, -0.5, Decimal("3.00"), "present"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_test_file_variants_when_parsing_then_it_returns_expected_raw_blocks(
    test_case: ParseSqlTestFileTestCase,
) -> None:
    discovered_blocks: tuple[DiscoveredSqlTestBlock, ...] = parse_sql_test_file(
        contents=test_case.contents, file_path=Path("tests/unit/orders.sql")
    )

    assert tuple(block.name for block in discovered_blocks) == test_case.expected_names
    assert tuple(block.sql_body for block in discovered_blocks) == test_case.expected_sql_bodies
    assert tuple(block.test_index for block in discovered_blocks) == test_case.expected_test_indexes
    assert tuple(block.header_values for block in discovered_blocks) == (
        test_case.expected_header_values
    )
    parameters: tuple[SqlTestParameterDeclaration, ...] = discovered_test_parameters(
        blocks=discovered_blocks
    )
    cases: tuple[DiscoveredSqlTestCase, ...] = discovered_test_cases(blocks=discovered_blocks)
    assert tuple(parameter.value_type.value for parameter in parameters) == (
        test_case.expected_parameter_types
    )
    assert tuple(parameter.nullable for parameter in parameters) == (
        test_case.expected_parameter_nullability
    )
    assert tuple(case.name for case in cases) == test_case.expected_case_names
    assert tuple(case.case_index for case in cases) == tuple(range(len(cases)))
    assert discovered_test_case_values(cases=cases) == test_case.expected_case_values


@pytest.mark.parametrize(
    "test_case",
    [
        ParseSqlTestFileErrorTestCase(
            description="raises when the file does not start with a test header",
            contents="SELECT 1\n",
            expected_error_fragment="must start with a TEST",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a single-test file of ctes omits its test header",
            contents=(
                "WITH __source__orders AS (SELECT 1 AS id),\n"
                "__expected__orders AS (SELECT 1 AS id)\n"
            ),
            expected_error_fragment=r"must start with a TEST\(\) header",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a body precedes another test block",
            contents='SELECT 1;\n\nTEST (name "second");\n\nSELECT 1\n',
            expected_error_fragment="must start with a TEST",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a test header is not terminated",
            contents='TEST (name "orders")\n\nWITH __source__orders AS (SELECT 1 AS id)\n',
            expected_error_fragment="must start with a TEST",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the file is empty",
            contents="\n  \n",
            expected_error_fragment="must start with a TEST",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when one block defines actual CTEs for several modes",
            contents=(
                "TEST();\n"
                "WITH __macro_actual__ AS (SELECT 1 AS a),\n__udf_actual__ AS (SELECT 1 AS a)\n"
            ),
            expected_error_fragment=r"actual CTEs for several test modes \(macro, udf\)",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when leading comments appear before the first test header",
            contents="-- comment\nTEST ();\n\nSELECT 1\n",
            expected_error_fragment="must start with a TEST",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a test block has no sql body",
            contents="TEST ();\n",
            expected_error_fragment="must define SQL after TEST(...)",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects the old colon syntax",
            contents="""
        TEST (name: "orders");

        SELECT 1
        """,
            expected_error_fragment="unexpected ':' after key 'name'",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the test header includes unsupported keys",
            contents="""
        TEST (name "orders", chain true);

        SELECT 1
        """,
            expected_error_fragment="unsupported keys: chain",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the test name is blank",
            contents="""
        TEST (name "   ");

        SELECT 1
        """,
            expected_error_fragment="must be a non-empty string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when the test name is not a string",
            contents="""
        TEST (name 123);

        SELECT 1
        """,
            expected_error_fragment="must be a non-empty string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects an explicit null test name",
            contents="TEST (name null);\n\nSELECT 1\n",
            expected_error_fragment="name.*must be a non-empty string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects an explicit null test mode with a discovery error",
            contents="TEST (mode null);\n\nSELECT 1\n",
            expected_error_fragment="mode.*must be a string",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a multi-block file leaves one block unnamed",
            contents="""
        TEST (name "first");

        SELECT 1;

        TEST ();

        SELECT 1
        """,
            expected_error_fragment="every block must define a unique `name`",
        ),
        ParseSqlTestFileErrorTestCase(
            description="raises when a multi-block file repeats a test name",
            contents="""
        TEST (name "shared");

        SELECT 1;

        TEST (name "shared");

        SELECT 1
        """,
            expected_error_fragment=r"defines duplicate TEST\(\) name 'shared'",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects duplicate header keys",
            contents='TEST (name "first", name "second");\n\nSELECT 1\n',
            expected_error_fragment="duplicate.*name",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects an unknown test mode",
            contents="TEST (mode integration);\n\nSELECT 1\n",
            expected_error_fragment="mode.*must be one of",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects parameters without cases",
            contents="TEST (parameters (status string));\n\nSELECT 1\n",
            expected_error_fragment="must define `parameters` and `cases` together",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects duplicate parameter names",
            contents=(
                "TEST (parameters (status string, status string), "
                'cases (one (status "open")));\nSELECT 1\n'
            ),
            expected_error_fragment="duplicate key 'status'",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects duplicate case names",
            contents=(
                "TEST (parameters (status string), cases ("
                'one (status "open"), one (status "closed")));\nSELECT 1\n'
            ),
            expected_error_fragment="duplicate key 'one'",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects missing case parameters",
            contents=(
                "TEST (parameters (status string, expected string), "
                'cases (one (status "open")));\nSELECT 1\n'
            ),
            expected_error_fragment="missing parameters: expected",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects undeclared case parameters",
            contents=(
                "TEST (parameters (status string), "
                'cases (one (status "open", expected "open")));\nSELECT 1\n'
            ),
            expected_error_fragment="undeclared parameters: expected",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects incompatible typed values",
            contents=('TEST (parameters (count integer), cases (one (count "1")));\nSELECT 1\n'),
            expected_error_fragment="has type str; expected integer",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects null for non-nullable parameters",
            contents="TEST (parameters (status string), cases (one (status null)));\nSELECT 1\n",
            expected_error_fragment="is not nullable",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects a cursor window outside model tests",
            contents='TEST (mode macro, cursor_start "2026-02-01");\nSELECT 1\n',
            expected_error_fragment=(
                "declares `cursor_start` or `cursor_end`, which are only supported for model "
                "tests, not mode 'macro'"
            ),
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects a boolean cursor bound",
            contents="TEST (cursor_end true);\nSELECT 1\n",
            expected_error_fragment="cursor_end in '.*' must be a non-empty string or an integer",
        ),
        ParseSqlTestFileErrorTestCase(
            description="rejects malformed case names",
            contents=(
                "TEST (parameters (status string), "
                'cases ("not valid" (status "open")));\nSELECT 1\n'
            ),
            expected_error_fragment="expected key",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_sql_test_file_contents_when_parsing_then_it_raises_clear_errors(
    test_case: ParseSqlTestFileErrorTestCase,
) -> None:
    with pytest.raises(SqlTestParseError, match=test_case.expected_error_fragment):
        parse_sql_test_file(contents=test_case.contents, file_path=Path("tests/unit/orders.sql"))


@pytest.mark.parametrize(
    "test_case",
    [
        ParseSqlTestModeTestCase(
            description="defaults to model mode without direct-logic actual CTEs",
            contents="TEST();\nWITH __source__orders AS (SELECT 1 AS id),\n__expected__orders AS (SELECT 1 AS id)",
            expected_modes=("model",),
            expected_header_values=({},),
        ),
        ParseSqlTestModeTestCase(
            description="infers macro mode under an empty header",
            contents=(
                "TEST();\n"
                "WITH __macro_actual__ AS (SELECT @double(1) AS value),\n"
                "__macro_expected__ AS (SELECT 2 AS value)"
            ),
            expected_modes=("macro",),
            expected_header_values=({},),
        ),
        ParseSqlTestModeTestCase(
            description="infers udf mode under a header without a mode",
            contents=(
                'TEST (name "detects_completed_orders");\n'
                "WITH __udf_actual__ AS (SELECT 1 AS value),\n"
                "__udf_expected__ AS (SELECT 1 AS value)\n"
                "SELECT 1"
            ),
            expected_modes=("udf",),
            expected_header_values=({"name": "detects_completed_orders"},),
        ),
        ParseSqlTestModeTestCase(
            description="infers table function mode from a lower-case as keyword",
            contents=(
                "TEST();\n"
                "WITH __table_fn_actual__ as (SELECT 1 AS value),\n"
                "__table_fn_expected__ as (SELECT 1 AS value)"
            ),
            expected_modes=("table_fn",),
            expected_header_values=({},),
        ),
        ParseSqlTestModeTestCase(
            description="infers each named block independently",
            contents=(
                'TEST (name "macro_case");\n'
                "WITH __macro_actual__ AS (SELECT 1 AS value),\n"
                "__macro_expected__ AS (SELECT 1 AS value);\n\n"
                'TEST (name "model_case");\n'
                "WITH __source__orders AS (SELECT 1 AS id),\n"
                "__expected__orders AS (SELECT 1 AS id)"
            ),
            expected_modes=("macro", "model"),
            expected_header_values=({"name": "macro_case"}, {"name": "model_case"}),
        ),
        ParseSqlTestModeTestCase(
            description="ignores actual CTE names in comments, strings and nested queries",
            contents=(
                "TEST();\n"
                "-- __macro_actual__ AS (\n"
                "WITH __source__orders AS (\n"
                "  WITH __udf_actual__ AS (SELECT 1 AS id) SELECT id FROM __udf_actual__\n"
                "),\n"
                "__expected__orders AS (SELECT '__table_fn_actual__ AS (' AS id)"
            ),
            expected_modes=("model",),
            expected_header_values=({},),
        ),
        ParseSqlTestModeTestCase(
            description="keeps an explicit mode even when it contradicts the CTEs",
            contents=(
                "TEST (mode model);\n"
                "WITH __macro_actual__ AS (SELECT 1 AS value),\n"
                "__macro_expected__ AS (SELECT 1 AS value)"
            ),
            expected_modes=("model",),
            expected_header_values=({"mode": "model"},),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_test_block_ctes_when_parsing_then_mode_is_explicit_or_inferred(
    test_case: ParseSqlTestModeTestCase,
) -> None:
    blocks: tuple[DiscoveredSqlTestBlock, ...] = parse_sql_test_file(
        contents=test_case.contents, file_path=Path("tests/unit/orders.sql")
    )

    assert tuple(block.mode.value for block in blocks) == test_case.expected_modes
    assert tuple(block.header_values for block in blocks) == test_case.expected_header_values


@pytest.mark.parametrize(
    "test_case",
    [
        ParseSqlTestCursorWindowTestCase(
            description="omitted keys leave the default window",
            contents='TEST (name "orders");\nSELECT 1\n',
            expected_cursor_start=None,
            expected_cursor_end=None,
        ),
        ParseSqlTestCursorWindowTestCase(
            description="timestamp bounds are kept as authored",
            contents=(
                'TEST (name "orders", cursor_start "2026-02-01", cursor_end "2026-02-03");\n'
                "SELECT 1\n"
            ),
            expected_cursor_start="2026-02-01",
            expected_cursor_end="2026-02-03",
        ),
        ParseSqlTestCursorWindowTestCase(
            description="integer bounds are normalized to text independently",
            contents='TEST (name "orders", cursor_end 20);\nSELECT 1\n',
            expected_cursor_start=None,
            expected_cursor_end="20",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_test_cursor_window_header_when_parsing_then_bounds_are_recorded(
    test_case: ParseSqlTestCursorWindowTestCase,
) -> None:
    blocks: tuple[DiscoveredSqlTestBlock, ...] = parse_sql_test_file(
        contents=test_case.contents, file_path=Path("tests/unit/orders.sql")
    )

    assert (blocks[0].cursor_start, blocks[0].cursor_end) == (
        test_case.expected_cursor_start,
        test_case.expected_cursor_end,
    )
