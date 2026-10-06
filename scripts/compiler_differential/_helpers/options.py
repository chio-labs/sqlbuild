"""Parse harness option values."""

from __future__ import annotations

import argparse
import re

from scripts.compiler_differential.constants import (
    EXPECT_FAILURE_PREFIX,
    EXPECT_SUCCESS,
    EXPECT_SUCCESS_VALUE,
)
from scripts.compiler_differential.exceptions import DifferentialUsageError
from scripts.compiler_differential.models import ExpectedOutcome

_DIAGNOSTIC_CODE: re.Pattern[str] = re.compile(r"[A-Z][A-Z0-9]*[0-9]")


def parse_engine_environment(values: list[str]) -> dict[str, dict[str, str]]:
    """Parse repeated `ENGINE:NAME=VALUE` options into per-engine environment overrides."""

    environment: dict[str, dict[str, str]] = {}
    for value in values:
        engine, separator, assignment = value.partition(":")
        name, equals, setting = assignment.partition("=")
        if not separator or not equals or not engine or not name:
            raise DifferentialUsageError(f"--engine-env expects ENGINE:NAME=VALUE, got {value!r}")
        environment.setdefault(engine, {})[name] = setting
    return environment


def parse_expected_outcome(value: str) -> ExpectedOutcome:
    """Parse `success` or `failure:<CODE>` into the outcome every --project must produce."""

    if value == EXPECT_SUCCESS_VALUE:
        return EXPECT_SUCCESS
    code: str = value.removeprefix(EXPECT_FAILURE_PREFIX)
    if code == value or not _DIAGNOSTIC_CODE.fullmatch(code):
        raise argparse.ArgumentTypeError(
            f"expected {EXPECT_SUCCESS_VALUE} or {EXPECT_FAILURE_PREFIX}<CODE>, got {value!r}"
        )
    return ExpectedOutcome(error_code=code)
