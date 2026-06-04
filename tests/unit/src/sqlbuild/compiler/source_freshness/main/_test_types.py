from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReadLatestSourceFreshnessTestCase:
    description: str
    rows: list[tuple[Any, ...]]
    expected_source_name: str
    expected_observed_at_iso: str


@dataclass(frozen=True)
class ReadLatestSourceFreshnessErrorTestCase:
    description: str
    read_error: Exception
    expected_message_fragment: str
