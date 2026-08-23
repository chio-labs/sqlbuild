"""Kata rule catalogue selection behavior tests."""

from pathlib import Path

import pytest

from sqlbuild.kata_engine._helpers.engine.catalogue import build_catalogue, select_rules
from sqlbuild.kata_engine.models import KataConfig, KataRule
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import (
    KataSelectionTestCase,
)

BUILT_IN_CODES: tuple[str, ...] = (
    "SQBKH001",
    "SQBKH002",
    "SQBKH101",
    "SQBKH201",
    "SQBKJ001",
    "SQBKJ002",
    "SQBKJ101",
    "SQBKL001",
    "SQBKL101",
    "SQBKN001",
    "SQBKN002",
    "SQBKN003",
    "SQBKR001",
    "SQBKR002",
    "SQBKR201",
    "SQBKR301",
    "SQBKR401",
    "SQBKS000",
    "SQBKS001",
    "SQBKS002",
    "SQBKS101",
    "SQBKS201",
    "SQBKS202",
    "SQBKS301",
    "SQBKS302",
    "SQBKS401",
    "SQBKS501",
    "SQBKX001",
    "SQBKX002",
    "SQBKX201",
)
STRUCTURE_CODES: tuple[str, ...] = (
    "SQBKS000",
    "SQBKS001",
    "SQBKS002",
    "SQBKS101",
    "SQBKS201",
    "SQBKS202",
    "SQBKS301",
    "SQBKS302",
    "SQBKS401",
    "SQBKS501",
)
NON_STRUCTURE_CODES: tuple[str, ...] = (
    "SQBKH001",
    "SQBKH002",
    "SQBKH101",
    "SQBKH201",
    "SQBKJ001",
    "SQBKJ002",
    "SQBKJ101",
    "SQBKL001",
    "SQBKL101",
    "SQBKN001",
    "SQBKN002",
    "SQBKN003",
    "SQBKR001",
    "SQBKR002",
    "SQBKR201",
    "SQBKR301",
    "SQBKR401",
    "SQBKX001",
    "SQBKX002",
    "SQBKX201",
)


@pytest.mark.parametrize(
    "test_case",
    (
        KataSelectionTestCase(
            description="built-in namespace activates every built-in",
            select=("SQBK",),
            ignore=(),
            expected_codes=BUILT_IN_CODES,
        ),
        KataSelectionTestCase(
            description="built-in family activates every family rule",
            select=("SQBKS",),
            ignore=(),
            expected_codes=STRUCTURE_CODES,
        ),
        KataSelectionTestCase(
            description="exact built-in code activates one rule",
            select=("SQBKS001",),
            ignore=(),
            expected_codes=("SQBKS001",),
        ),
        KataSelectionTestCase(
            description="empty selection activates no rules",
            select=(),
            ignore=(),
            expected_codes=(),
        ),
        KataSelectionTestCase(
            description="ignored family is removed from selected namespace",
            select=("SQBK",),
            ignore=("SQBKS",),
            expected_codes=NON_STRUCTURE_CODES,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_rule_selectors_when_resolving_then_returns_expected_codes(
    tmp_path: Path,
    test_case: KataSelectionTestCase,
) -> None:
    config: KataConfig = KataConfig(select=test_case.select, ignore=test_case.ignore)
    catalogue: tuple[KataRule, ...] = build_catalogue(config=config, project_dir=tmp_path)

    selected: tuple[KataRule, ...] = select_rules(catalogue=catalogue, config=config)

    assert tuple(rule.code for rule in selected) == test_case.expected_codes
