from dataclasses import dataclass


@dataclass(frozen=True)
class NativeStubDriftTestCase:
    description: str
    stub_text: str
    registered: frozenset[str]
    expected_drift: tuple[str, ...]
