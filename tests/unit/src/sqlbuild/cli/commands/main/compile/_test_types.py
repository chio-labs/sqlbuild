from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TargetWriterTestCase:
    description: str
    expected_files: dict[str, str] = field(default_factory=dict)
    expected_summary_line: str = ""


@dataclass(frozen=True)
class ResolveAdapterTestCase:
    description: str
    adapter_name: str
    expected_adapter_class_name: str


@dataclass(frozen=True)
class ResolveAdapterErrorTestCase:
    description: str
    adapter_name: str
    expected_error_fragment: str
