from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class MacroBridgeFailureTestCase:
    """A render stage that fails with the macro bridge active."""

    description: str
    stage_with_bridge: Callable[[], str]
    stage_without_bridge: Callable[[], str]
    expected_error: type[Exception]
    expected_bridged_runs: list[bool]


@dataclass(frozen=True)
class MacroBridgeSuccessTestCase:
    """A render stage that succeeds with the macro bridge active."""

    description: str
    expected_result: str
    expected_bridged_runs: list[bool]


@dataclass(frozen=True)
class MacroBridgeErrorContextTestCase:
    """A stage whose Python error must not chain the bridge failure as its context."""

    description: str
    stage: Callable[[], str]
    expected_context: BaseException | None
