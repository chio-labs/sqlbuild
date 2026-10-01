"""Latest fingerprint set assembly shared by warehouse reads and in-memory selection."""

from __future__ import annotations

from collections.abc import Iterable

from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_MODEL
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet


def build_latest_fingerprint_set(*, schema: str, latest: Iterable[Fingerprint]) -> FingerprintSet:
    """Index latest rows by identity and by node name, preferring models on name collisions."""

    fingerprints: dict[str, Fingerprint] = {}
    fingerprints_by_identity: dict[tuple[str, str], Fingerprint] = {}
    fingerprint: Fingerprint
    for fingerprint in latest:
        fingerprints_by_identity[(fingerprint.node_type, fingerprint.node_name)] = fingerprint
        if fingerprint.node_type == NODE_TYPE_MODEL or fingerprint.node_name not in fingerprints:
            fingerprints[fingerprint.node_name] = fingerprint
    return FingerprintSet(
        schema=schema,
        fingerprints=fingerprints,
        fingerprints_by_identity=fingerprints_by_identity,
    )
