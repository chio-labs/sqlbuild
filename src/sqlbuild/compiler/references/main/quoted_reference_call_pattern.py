"""Public quoted SQL reference pattern entry."""

from __future__ import annotations

import re

from sqlbuild.compiler.references.helpers.patterns import (
    quoted_reference_call_pattern as _quoted_reference_call_pattern,
)
from sqlbuild.compiler.references.types import SqlReferenceKind


def quoted_reference_call_pattern(kind: SqlReferenceKind) -> re.Pattern[str]:
    return _quoted_reference_call_pattern(kind)
