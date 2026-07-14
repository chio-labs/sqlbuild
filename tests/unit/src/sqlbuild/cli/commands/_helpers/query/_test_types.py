from dataclasses import dataclass

from sqlbuild.adapter.contract.models import QueryResult


@dataclass(frozen=True)
class QueryOutputTestCase:
    description: str
    result: QueryResult
    output_format: str
    limit: int | None
    expected_output: str
