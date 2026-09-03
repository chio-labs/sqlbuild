from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionContractCase:
    description: str
    expected_abstract: bool
