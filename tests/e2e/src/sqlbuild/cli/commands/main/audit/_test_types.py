"""Test types for audit command e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuditE2ETestCase:
    """Test case for sqb audit e2e verification."""

    description: str
    expected_exit_code: int
    expected_stdout_fragment: str
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_ordered_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
