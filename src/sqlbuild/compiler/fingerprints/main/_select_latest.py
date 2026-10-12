"""In-memory node selection over an unfiltered latest fingerprint read."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.fingerprints.models import FingerprintSet


def select_latest_fingerprints(
    *,
    fingerprint_set: FingerprintSet,
    node_names: tuple[str, ...],
    filtered_node_types: tuple[str, ...] = (),
) -> FingerprintSet:
    """Apply the ``read_latest_fingerprints`` node filter to an unfiltered latest read."""

    return _native.select_latest_fingerprints(fingerprint_set, node_names, filtered_node_types)
