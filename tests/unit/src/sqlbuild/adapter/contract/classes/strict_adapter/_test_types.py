from dataclasses import dataclass


@dataclass(frozen=True)
class StrictAdapterContractTestCase:
    description: str
    expected_missing_methods: frozenset[str]


@dataclass(frozen=True)
class FirstClassAdapterImplementationContractTestCase:
    description: str
    expected_violations: tuple[str, ...]


@dataclass(frozen=True)
class TableFreshnessMetadataUnsupportedTestCase:
    description: str
    expected_supports_metadata: bool
    expected_error_fragment: str


@dataclass(frozen=True)
class OptionalStrictMethodTestCase:
    description: str
    expected_optional_methods: frozenset[str]
    expected_output_relation: None


@dataclass(frozen=True)
class StrictAdapterInlineSqlTestTestCase:
    description: str
    expected_total: int
    expected_outcome: str
    expected_statement_count: int
