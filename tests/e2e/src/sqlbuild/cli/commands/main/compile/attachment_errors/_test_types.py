from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeAttachmentErrorTestCase:
    """One failing attachment project compiled by every engine through the CLI."""

    description: str
    case_name: str
    expected_macro_calls: tuple[int, int, int]
    expected_error_types: tuple[str, str, str]
