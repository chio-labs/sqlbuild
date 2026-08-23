from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionReturnContractIdentityTestCase:
    description: str
    original_type: str
    changed_type: str
    expected_changed: bool


@dataclass(frozen=True)
class FunctionUpstreamIdentityTestCase:
    description: str
    original_query: str
    changed_query: str
    expected_changed: bool
