"""Test types for reconcile e2e tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReconcileE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_fragments: tuple[str, ...]
    expected_exit_code: int = 0
    expected_query_results: tuple[tuple[str, tuple[tuple[object, ...], ...]], ...] = field(
        default_factory=tuple
    )
    input_text: str | None = None
