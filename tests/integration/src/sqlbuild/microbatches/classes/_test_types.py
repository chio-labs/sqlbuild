from dataclasses import dataclass


@dataclass(frozen=True)
class DirectStorePublicationTestCase:
    description: str
    event_count: int
    expected_total: int
    expected_inserted: int
    expected_already_existing: int
    expected_statement_count: int


@dataclass(frozen=True)
class DirectStoreSuccessiveWriteTestCase:
    description: str
    initial_event_count: int
    successive_event_count: int
    expected_initial_statement_count: int
    expected_successive_statement_count: int
    expected_initialization_statement_count: int
