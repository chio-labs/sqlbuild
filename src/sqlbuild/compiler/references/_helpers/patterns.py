"""Regex helpers for SQLBuild reference function syntax."""

from __future__ import annotations

import re

from sqlbuild.compiler.references.types import SqlReferenceKind


def reference_call_prefix_pattern_text(kind: SqlReferenceKind) -> str:
    return rf"{re.escape(kind.function_name)}\("


def quoted_reference_call_pattern_text(kind: SqlReferenceKind) -> str:
    return rf'{reference_call_prefix_pattern_text(kind)}"([^"]+)"\)'


def quoted_reference_call_pattern(kind: SqlReferenceKind) -> re.Pattern[str]:
    return re.compile(quoted_reference_call_pattern_text(kind))
