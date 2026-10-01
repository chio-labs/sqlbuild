"""In-memory node selection over an unfiltered latest fingerprint read."""

from __future__ import annotations

from sqlbuild.compiler.fingerprints._helpers.latest import build_latest_fingerprint_set
from sqlbuild.compiler.fingerprints.models import FingerprintSet


def select_latest_fingerprints(
    *,
    fingerprint_set: FingerprintSet,
    node_names: tuple[str, ...],
    filtered_node_types: tuple[str, ...] = (),
) -> FingerprintSet:
    """Apply the ``read_latest_fingerprints`` node filter to an unfiltered latest read."""

    if not node_names and not filtered_node_types:
        return FingerprintSet(schema=fingerprint_set.schema, fingerprints={})
    names: frozenset[str] = frozenset(node_names)
    types: frozenset[str] = frozenset(filtered_node_types)
    return build_latest_fingerprint_set(
        schema=fingerprint_set.schema,
        latest=(
            fingerprint
            for fingerprint in (fingerprint_set.fingerprints_by_identity or {}).values()
            if fingerprint.node_name in names or (types and fingerprint.node_type not in types)
        ),
    )
