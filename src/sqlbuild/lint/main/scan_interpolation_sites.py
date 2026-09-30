"""Public lexical scan for SQLBuild interpolation sites in authored SQL."""

from __future__ import annotations

from sqlbuild.lint._helpers.sqlbuild_tokens import neutralize_interpolation
from sqlbuild.lint.models import InterpolationSite


def scan_interpolation_sites(*, body: str, dialect: str) -> tuple[InterpolationSite, ...]:
    """Return every reference call, macro, and template site outside comments and strings."""

    return neutralize_interpolation(body=body, dialect=dialect)[1]
