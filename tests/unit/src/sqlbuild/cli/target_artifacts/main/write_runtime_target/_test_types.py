from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TargetWriterTestCase:
    description: str
    expected_files: dict[str, str] = field(default_factory=dict)
    initial_files: dict[str, str] = field(default_factory=dict)
