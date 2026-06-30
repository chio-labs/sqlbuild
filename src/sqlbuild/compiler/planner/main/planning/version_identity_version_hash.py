"""Public entrypoint for composed model version identity hashing."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.planner.helpers.shared.identity_hashing import (
    build_model_version_identity_hash as _build_model_version_identity_hash,
)


def build_model_version_identity_hash(
    *,
    local_hash: str,
    upstream_deps: tuple[CompiledObjectKey, ...],
    upstream_version_hashes: dict[str, str],
    source_version_hashes: dict[str, str] | None = None,
) -> str:
    """Build a composed model version hash from local and upstream identities."""

    return _build_model_version_identity_hash(
        local_hash=local_hash,
        upstream_deps=upstream_deps,
        upstream_version_hashes=upstream_version_hashes,
        source_version_hashes=source_version_hashes,
    )
