from dataclasses import dataclass


@dataclass(frozen=True)
class OutputStreamEncodingTestCase:
    description: str
    encoding: str
    errors: str
    text: str
    expected_changed: bool
    expected_bytes: bytes
