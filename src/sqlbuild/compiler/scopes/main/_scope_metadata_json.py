"""Serialize safe default scope metadata to canonical JSON."""

from __future__ import annotations

import json

from sqlbuild.compiler.scopes._helpers.report_projection import (
    build_projection as scope_metadata_projection,
)
from sqlbuild.compiler.scopes.models import ScopeIndex


def scope_metadata_json(*, index: ScopeIndex) -> str:
    """Serialize default scope metadata to byte-stable canonical JSON."""

    return json.dumps(
        scope_metadata_projection(index=index),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
