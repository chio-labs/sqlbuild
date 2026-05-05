from dataclasses import dataclass


@dataclass(frozen=True)
class StrictAdapterContractTestCase:
    description: str
    expected_missing_methods: frozenset[str]
