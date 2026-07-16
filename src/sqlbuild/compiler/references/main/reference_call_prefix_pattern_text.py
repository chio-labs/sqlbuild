"""Public SQL reference prefix pattern entry."""

from __future__ import annotations

from sqlbuild.compiler.references._helpers.patterns import (
    reference_call_prefix_pattern_text as _reference_call_prefix_pattern_text,
)
from sqlbuild.compiler.references.types import SqlReferenceKind


def reference_call_prefix_pattern_text(kind: SqlReferenceKind) -> str:
    return _reference_call_prefix_pattern_text(kind)
