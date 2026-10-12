from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeAttachmentErrorTestCase:
    """One failing attachment project compiled through the CLI."""

    description: str
    case_name: str
    expected_macro_calls: int
    expected_error_type: str
