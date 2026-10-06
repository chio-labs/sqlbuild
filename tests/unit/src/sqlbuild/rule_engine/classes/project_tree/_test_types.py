from dataclasses import dataclass


@dataclass(frozen=True)
class ReadTextTestCase:
    description: str
    path: str
    expected_text: str | None = None
    expected_error: str = ""
