"""Tests for mode-specific janitor retention resolution."""

from __future__ import annotations

import pytest

from sqlbuild.executor.janitor.main.resolve_retention_days import resolve_janitor_retention_days
from tests.unit.src.sqlbuild.executor.janitor.main._test_types import (
    JanitorRetentionResolutionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorRetentionResolutionTestCase(
            description="unset retention in direct mode defaults to 14",
            override=None,
            configured=None,
            virtual_environments=False,
            expected_retention_days=14,
        ),
        JanitorRetentionResolutionTestCase(
            description="unset retention in virtual mode defaults to 30",
            override=None,
            configured=None,
            virtual_environments=True,
            expected_retention_days=30,
        ),
        JanitorRetentionResolutionTestCase(
            description="explicit retention applies in direct mode",
            override=None,
            configured=7,
            virtual_environments=False,
            expected_retention_days=7,
        ),
        JanitorRetentionResolutionTestCase(
            description="explicit retention applies in virtual mode",
            override=None,
            configured=7,
            virtual_environments=True,
            expected_retention_days=7,
        ),
        JanitorRetentionResolutionTestCase(
            description="cli override wins over explicit config",
            override=3,
            configured=7,
            virtual_environments=True,
            expected_retention_days=3,
        ),
        JanitorRetentionResolutionTestCase(
            description="cli zero override wins over the mode default",
            override=0,
            configured=None,
            virtual_environments=True,
            expected_retention_days=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_retention_inputs_when_resolving_janitor_retention_then_returns_expected_days(
    test_case: JanitorRetentionResolutionTestCase,
) -> None:
    resolved: int = resolve_janitor_retention_days(
        override=test_case.override,
        configured=test_case.configured,
        virtual_environments=test_case.virtual_environments,
    )

    assert resolved == test_case.expected_retention_days
