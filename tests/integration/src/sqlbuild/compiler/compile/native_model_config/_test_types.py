"""Test case types for the native model validator error tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeErrorTestCase:
    """An invalid config and the exact error the native validators raise for it."""

    description: str
    values: dict[str, object]
    expected_outcome: object
