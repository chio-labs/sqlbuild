"""Public selector parsing entrypoint for planner consumers."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.graph.selectors import parse_selector
from sqlbuild.compiler.planner.models import ParsedSelector, PathSelector


def parse_project_selector(raw: str) -> ParsedSelector | PathSelector:
    """Parse one project selector token into a structured form."""

    return parse_selector(raw)
