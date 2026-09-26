"""Validation for the optional scenario artifact run namespace."""

from __future__ import annotations

import re

from sqlbuild.spec.contracts.exceptions import SpecConfigError


def parse_scenario_run_namespace(value: object) -> str:
    """Return a valid namespace or reject it without normalization."""

    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value) is None:
        raise SpecConfigError(
            "scenario.run_namespace must be 1–128 characters: "
            "ASCII letters, digits, '-', '_' or '.'"
        )
    return value
