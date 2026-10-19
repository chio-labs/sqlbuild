from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.clickhouse._helpers.partition_rewrite import artifact_relation
from sqlbuild.adapters.clickhouse._helpers.snapshot_rewrite import (
    nullable_offset_windows,
    rewrite_snapshot_statements,
)
from sqlbuild.adapters.clickhouse._helpers.type_text import (
    canonical_type,
    nullable_type,
    quote_string,
)
from sqlbuild.adapters.clickhouse.models import SnapshotWorkspace
from tests.unit.src.sqlbuild.adapters.clickhouse._test_types import (
    ArtifactRelationTestCase,
    CanonicalTypeTestCase,
    NullableOffsetWindowTestCase,
    NullableTypeTestCase,
    QuoteStringTestCase,
    SnapshotCloseRewriteTestCase,
    UnsupportedSnapshotStatementTestCase,
)

_WORKSPACE: SnapshotWorkspace = SnapshotWorkspace(
    destination="sales.customers",
    work="sales.customers__w",
    rebuild="sales.customers__r",
    valid_to_column="valid_to",
)


@pytest.mark.parametrize(
    "test_case",
    [
        CanonicalTypeTestCase("nullable integer", "Nullable(Int64)", "BIGINT"),
        CanonicalTypeTestCase(
            "low cardinality string", "LowCardinality(Nullable(String))", "VARCHAR"
        ),
        CanonicalTypeTestCase("parameterized decimal", "Decimal(18, 4)", "DECIMAL(18, 4)"),
        CanonicalTypeTestCase("sized decimal", "Decimal64(2)", "DECIMAL(18, 2)"),
        CanonicalTypeTestCase("timestamp", "DateTime64(6, 'UTC')", "TIMESTAMP"),
        CanonicalTypeTestCase("unknown type kept", "Array(Int64)", "Array(Int64)"),
    ],
    ids=lambda case: case.description,
)
def test_given_clickhouse_type_when_canonicalizing_then_shared_spelling_returns(
    test_case: CanonicalTypeTestCase,
) -> None:
    assert canonical_type(test_case.type_sql) == test_case.expected_type


@pytest.mark.parametrize(
    "test_case",
    [
        NullableTypeTestCase("scalar wraps", "Int64", "Nullable(Int64)"),
        NullableTypeTestCase("already nullable", "Nullable(String)", "Nullable(String)"),
        NullableTypeTestCase(
            "low cardinality wraps inside",
            "LowCardinality(String)",
            "LowCardinality(Nullable(String))",
        ),
        NullableTypeTestCase("arrays cannot wrap", "Array(Int64)", "Array(Int64)"),
    ],
    ids=lambda case: case.description,
)
def test_given_column_type_when_making_nullable_then_clickhouse_rules_apply(
    test_case: NullableTypeTestCase,
) -> None:
    assert nullable_type(test_case.type_sql) == test_case.expected_type


@pytest.mark.parametrize(
    "test_case",
    [
        QuoteStringTestCase(
            description="backslash and quote both escape",
            value="it's a\\b",
            expected_literal="'it\\'s a\\\\b'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_backslash_and_quote_when_quoting_then_both_escape(
    test_case: QuoteStringTestCase,
) -> None:
    assert quote_string(test_case.value) == test_case.expected_literal


@pytest.mark.parametrize(
    "test_case",
    [
        ArtifactRelationTestCase(
            description="long names are cut to the identifier limit",
            relation="sales." + "x" * 300,
            expected_prefix='sales."x',
            expected_name_length=200,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_long_name_when_naming_artifact_then_identifier_limit_holds(
    test_case: ArtifactRelationTestCase,
) -> None:
    relation: str = artifact_relation(relation=test_case.relation, infix="__sqb_rw_", digest="abc")

    assert relation.startswith(test_case.expected_prefix)
    assert len(relation.split(".", 1)[1].strip('"')) == test_case.expected_name_length


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotCloseRewriteTestCase(
            description="joined close keeps its source",
            statement=(
                "UPDATE sales.customers__w AS __target SET valid_to = __source.updated_at "
                "FROM (SELECT * FROM src WHERE x = 1) AS __source "
                "WHERE __target.customer_id = __source.customer_id AND __target.valid_to IS NULL"
            ),
            expected_close_select=(
                "SELECT sipHash128(__target.* EXCEPT (valid_to)) AS __sqb_row, "
                "min(__source.updated_at) AS __sqb_valid_to, 1 AS __sqb_closed "
                "FROM sales.customers__w AS __target, "
                "(SELECT * FROM src WHERE x = 1) AS __source WHERE "
                "__target.customer_id = __source.customer_id AND __target.valid_to IS NULL "
                "GROUP BY __sqb_row"
            ),
        ),
        SnapshotCloseRewriteTestCase(
            description="hard delete close has no join",
            statement=(
                "UPDATE sales.customers__w AS __target SET valid_to = now64(6, 'UTC') "
                "WHERE __target.valid_to IS NULL AND NOT EXISTS (SELECT 1 FROM src AS __source "
                "WHERE __source.customer_id = __target.customer_id)"
            ),
            expected_close_select=(
                "SELECT sipHash128(__target.* EXCEPT (valid_to)) AS __sqb_row, "
                "min(now64(6, 'UTC')) AS __sqb_valid_to, 1 AS __sqb_closed "
                "FROM sales.customers__w AS __target "
                "WHERE __target.valid_to IS NULL AND NOT EXISTS (SELECT 1 FROM src AS __source "
                "WHERE __source.customer_id = __target.customer_id) GROUP BY __sqb_row"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_close_when_rewriting_then_working_copy_is_rebuilt_and_exchanged(
    test_case: SnapshotCloseRewriteTestCase,
) -> None:
    statements: tuple[str, ...] = rewrite_snapshot_statements(
        workspace=_WORKSPACE,
        statements=("INSERT INTO sales.customers__w SELECT 1", test_case.statement),
    )

    assert statements[:5] == (
        "DROP TABLE IF EXISTS sales.customers__w",
        "DROP TABLE IF EXISTS sales.customers__r",
        "CREATE TABLE sales.customers__w AS sales.customers COMMENT ''",
        "INSERT INTO sales.customers__w SELECT * FROM sales.customers",
        "INSERT INTO sales.customers__w SELECT 1",
    )
    assert test_case.expected_close_select in statements[6]
    assert statements[-4:] == (
        "EXCHANGE TABLES sales.customers__w AND sales.customers__r",
        "DROP TABLE sales.customers__r",
        "EXCHANGE TABLES sales.customers AND sales.customers__w",
        "DROP TABLE IF EXISTS sales.customers__w",
    )


@pytest.mark.parametrize(
    "test_case",
    [
        UnsupportedSnapshotStatementTestCase(
            description="update of another relation",
            statement="UPDATE other SET valid_to = 1 WHERE 1",
            expected_code="A709",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unrecognized_update_when_rewriting_then_coded_error_names_it(
    test_case: UnsupportedSnapshotStatementTestCase,
) -> None:
    with pytest.raises(AdapterUserError) as error:
        rewrite_snapshot_statements(workspace=_WORKSPACE, statements=(test_case.statement,))

    assert error.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        NullableOffsetWindowTestCase(
            description="lag and lead arguments become nullable",
            statement=(
                "SELECT LAG(__observed_at) OVER (ORDER BY __observed_at), "
                "LEAD(__new_changes.updated_at) OVER (PARTITION BY k ORDER BY x), lag_value FROM t"
            ),
            expected_statement=(
                "SELECT LAG(toNullable(__observed_at)) OVER (ORDER BY __observed_at), "
                "LEAD(toNullable(__new_changes.updated_at)) OVER (PARTITION BY k ORDER BY x), "
                "lag_value FROM t"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_offset_windows_when_rewriting_then_arguments_become_nullable(
    test_case: NullableOffsetWindowTestCase,
) -> None:
    assert nullable_offset_windows((test_case.statement,)) == (test_case.expected_statement,)
