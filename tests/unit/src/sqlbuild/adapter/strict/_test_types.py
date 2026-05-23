from dataclasses import dataclass


@dataclass(frozen=True)
class StrictAdapterContractTestCase:
    description: str
    expected_missing_methods: frozenset[str]


@dataclass(frozen=True)
class FirstClassAdapterImplementationContractTestCase:
    description: str
    expected_violations: tuple[str, ...]
