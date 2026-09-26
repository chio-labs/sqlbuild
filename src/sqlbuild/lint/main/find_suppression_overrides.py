"""Expose inline opt-outs to compiler policy enforcement."""

from pathlib import Path

from sqlbuild.lint._helpers.suppressions import find_suppression_overrides as find
from sqlbuild.lint.models import LintViolation


def find_suppression_overrides(*, contents_by_path: dict[Path, str]) -> tuple[LintViolation, ...]:
    return find(contents_by_path=contents_by_path)
