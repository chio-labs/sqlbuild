"""Statement classification and the Snowflake session hook stay linear on adversarial SQL."""

from __future__ import annotations

import time

import pytest

from sqlbuild.adapter.relations._helpers.ddl_effects import statement_metadata_effect
from sqlbuild.adapters.snowflake._helpers.session_context import may_switch_session_database
from tests.unit.src.sqlbuild.adapter.relations._helpers.ddl_effects._test_types import (
    AdversarialStatementTestCase,
)

_REALISTIC_CTAS: str = (
    "CREATE OR REPLACE TABLE analytics.marts.orders AS SELECT "
    + ", ".join(f'CAST(col_{index} AS VARCHAR) AS "c{index}" -- note\n' for index in range(25_000))
    + " FROM raw.orders WHERE status = 'it''s' AND body = $$x$$"
)


@pytest.mark.parametrize(
    "test_case",
    [
        AdversarialStatementTestCase(
            description="10k leading spaces",
            sql=" " * 10_000 + "SELECT 1",
        ),
        AdversarialStatementTestCase(
            description="100k leading spaces",
            sql=" " * 100_000 + "SELECT 1",
        ),
        AdversarialStatementTestCase(
            description="100k mixed leading whitespace",
            sql="\n\t " * 33_000 + "USE DATABASE analytics",
        ),
        AdversarialStatementTestCase(
            description="repeated unterminated block comments",
            sql="/*" * 20_000,
        ),
        AdversarialStatementTestCase(
            description="spaced unterminated block comments",
            sql="SELECT " + "/* " * 20_000,
        ),
        AdversarialStatementTestCase(
            description="many dollar tag openers",
            sql="SELECT " + "$a$ " * 10_000,
        ),
        AdversarialStatementTestCase(
            description="many unclosed dollar tags",
            sql="SELECT " + "$tag" * 10_000,
        ),
        AdversarialStatementTestCase(
            description="drop with long whitespace and junk",
            sql="DROP TABLE marts.orders" + " " * 20_000 + "x",
        ),
        AdversarialStatementTestCase(
            description="create with long whitespace and junk",
            sql="CREATE TABLE marts.orders" + " " * 20_000 + "x",
        ),
        AdversarialStatementTestCase(
            description="alter with long whitespace and junk",
            sql="ALTER TABLE marts.orders" + " " * 20_000 + "x",
        ),
        AdversarialStatementTestCase(
            description="many single quotes",
            sql="SELECT " + "'" * 20_001,
        ),
        AdversarialStatementTestCase(
            description="many double quotes",
            sql="SELECT " + '"' * 20_001,
        ),
        AdversarialStatementTestCase(
            description="many line comments",
            sql="-- c\n" * 20_000 + "SELECT 1",
        ),
        AdversarialStatementTestCase(
            description="1 MB create table as select",
            sql=_REALISTIC_CTAS,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adversarial_sql_when_scanning_then_completes_within_bound(
    test_case: AdversarialStatementTestCase,
) -> None:
    classifier_started: float = time.perf_counter()
    _ = statement_metadata_effect(test_case.sql)
    classifier_seconds: float = time.perf_counter() - classifier_started
    hook_started: float = time.perf_counter()
    _ = may_switch_session_database(test_case.sql)
    hook_seconds: float = time.perf_counter() - hook_started

    assert classifier_seconds < test_case.expected_max_seconds
    assert hook_seconds < test_case.expected_max_seconds


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
