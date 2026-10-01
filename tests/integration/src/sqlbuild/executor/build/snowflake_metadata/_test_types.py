from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuildMetadataBudgetTestCase:
    """Two consecutive offline Snowflake builds and the column reads each may issue."""

    description: str
    max_concurrency: int
    expected_first_column_reads: dict[str, int]
    expected_second_column_reads: dict[str, int]


@dataclass(frozen=True)
class SchemaEvolutionTestCase:
    """A merge model whose delta gains a column between builds."""

    description: str
    added_column: str
    expected_target_reads: int
    expected_merge_fragment: str
