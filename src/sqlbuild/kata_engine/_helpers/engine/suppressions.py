"""Kata fault suppression and stale-exemption validation."""

import re
from fnmatch import fnmatch
from pathlib import Path

from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import KataConfig, KataFault, KataRule


def apply_suppressions(*, faults: list[KataFault], config: KataConfig) -> list[KataFault]:
    """Return faults not covered by exact exemptions or scoped ignores."""

    visible: list[KataFault] = []
    for fault in faults:
        exact: bool = any(
            entry.rule == fault.code and entry.path == fault.path.as_posix()
            for entry in config.rule_exceptions
        )
        ignored: bool = False
        for entry in config.rule_ignores:
            rule_matches: bool = any(fault.code.startswith(selector) for selector in entry.rules)
            path_matches: bool = any(
                fnmatch(fault.path.as_posix(), pattern) for pattern in entry.paths
            )
            if rule_matches and path_matches:
                ignored = True
                break
        if not exact and not ignored:
            visible.append(fault)
    return visible


def validate_exception_codes(*, config: KataConfig, catalogue: tuple[KataRule, ...]) -> None:
    """Reject exact exemptions targeting unknown rules."""

    codes: frozenset[str] = frozenset(rule.code for rule in catalogue)
    unknown: tuple[str, ...] = tuple(
        sorted({entry.rule for entry in config.rule_exceptions if entry.rule not in codes})
    )
    if unknown:
        raise KataError(f"kata exceptions target unknown rules: {', '.join(unknown)}")
    for ignore in config.rule_ignores:
        for selector in ignore.rules:
            if not re.fullmatch(r"(?:KT[A-Z]?\d{0,3}|X[A-Z]*\d{0,3})", selector):
                raise KataError(f"malformed kata rule-ignore selector: {selector}")
            if not any(rule.code.startswith(selector) for rule in catalogue):
                raise KataError(f"kata rule-ignore selector matches no rules: {selector}")


def validate_exceptions(*, config: KataConfig, faults: list[KataFault], project_dir: Path) -> None:
    """Reject exemptions whose path or matching fault no longer exists."""

    for entry in config.rule_exceptions:
        path: Path = project_dir / entry.path
        if not path.is_file():
            raise KataError(f"kata exception path does not exist: {entry.path}")
        matched: bool = any(
            fault.code == entry.rule and fault.path.as_posix() == entry.path for fault in faults
        )
        if not matched:
            raise KataError(
                f"stale kata exception suppresses no fault: {entry.rule} at {entry.path}"
            )
