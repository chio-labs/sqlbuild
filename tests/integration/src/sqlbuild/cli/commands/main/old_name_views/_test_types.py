"""Test case types for old-name compatibility view integration tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class OldNameResumeTestCase:
    description: str
    install_failure: Callable[[pytest.MonkeyPatch], None]
    expected_first_exit_code: int
    expected_facts_after_failure: tuple[str, ...]
    expected_old_name_type_after_failure: str | None
    expected_final_facts: tuple[str, ...]
    expected_archive_count: int


@dataclass(frozen=True)
class OldNameJanitorResumeTestCase:
    description: str
    early_drop: tuple[str, ...]
    expected_facts_after_crash: tuple[str, ...]
    expected_retry_fragment: str
    expected_final_facts: tuple[str, ...]


@dataclass(frozen=True)
class OldNameResumeSkipTestCase:
    description: str
    install_failure: Callable[[pytest.MonkeyPatch], None]
    retry_models: dict[str, str]
    expected_plan_fragment: str
    expected_facts: tuple[str, ...]
    expected_old_name_type: str | None
    expected_old_name_ids: tuple[int, ...] | None
