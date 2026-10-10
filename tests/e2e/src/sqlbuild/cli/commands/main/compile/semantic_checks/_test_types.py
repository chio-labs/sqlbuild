from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeSemanticChecksCliTestCase:
    """Every engine compiling one failing project through the CLI with identical diagnostics."""

    description: str
    files: dict[str, str]
    expected_codes: tuple[str, ...]
    expected_notes: tuple[str, ...]
