"""Parse harness option values."""

from __future__ import annotations

import argparse
import re

from scripts.compiler_differential.constants import (
    EXPECT_FAILURE_PREFIX,
    EXPECT_SUCCESS,
    EXPECT_SUCCESS_VALUE,
)
from scripts.compiler_differential.models import ExpectedOutcome

_DIAGNOSTIC_CODE: re.Pattern[str] = re.compile(r"[A-Z][A-Z0-9]*[0-9]")


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
