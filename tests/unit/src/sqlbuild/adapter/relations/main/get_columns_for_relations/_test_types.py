from dataclasses import dataclass


@dataclass(frozen=True)
class QualifiedBulkColumnsTestCase:
    description: str
    expected_query_count: int
    expected_identity_count: int
    expected_names_filter_is_none: bool = False
