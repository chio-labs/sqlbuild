from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeSemanticChecksCliTestCase:
    """One failing project compiled through the CLI and its diagnostics."""

    description: str
    files: dict[str, str]
    expected_codes: tuple[str, ...]
    expected_notes: tuple[str, ...]
