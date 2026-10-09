from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class MacroBridgeFailureTestCase:
    """A render stage that fails with the macro bridge active."""

    description: str
    stage_with_bridge: Callable[[], str]
    expected_error_message: str
    expected_bridged_runs: list[bool]


@dataclass(frozen=True)
class MacroBridgeSuccessTestCase:
    """A render stage that succeeds with the macro bridge active."""

    description: str
    expected_result: str
    expected_bridged_runs: list[bool]
