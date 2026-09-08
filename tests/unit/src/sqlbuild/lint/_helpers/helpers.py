"""Shared builders for lint helper unit tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.lint import CustomLintFinding, LintRuleContext, lint_rule
from sqlbuild.lint._helpers.headers import scan_headers, sql_body_ranges
from sqlbuild.lint.models import HeaderSpan, LintBody


def lint_bodies_for(*, file_path: Path, contents: str) -> tuple[LintBody, ...]:
    """Build unexpanded lint bodies for every SQL body in the contents."""

    headers: tuple[HeaderSpan, ...] = scan_headers(contents=contents)
    bodies: list[LintBody] = []
    body_start: int
    body_end: int
    for body_start, body_end in sql_body_ranges(contents=contents, headers=headers):
        bodies.append(
            LintBody(
                file_path=file_path,
                body_start=body_start,
                body_end=body_end,
                lint_text=contents[body_start:body_end],
                passes=(),
            )
        )
    return tuple(bodies)


@lint_rule(
    code="XSQBLS001",
    family="shape",
    slug="no-star",
    message="Star is forbidden",
    remediation="Enumerate columns.",
)
def no_star(*, ctx: LintRuleContext) -> tuple[CustomLintFinding, ...]:
    """Report a star projection without exposing project capabilities."""

    assert not hasattr(ctx, "model")
    assert not hasattr(ctx, "project")
    start: int = ctx.source.index("*")
    return (ctx.finding(start=start, end=start + 1),)
