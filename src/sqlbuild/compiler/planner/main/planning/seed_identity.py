"""Public entrypoint for seed version identity hashing."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledSeed
from sqlbuild.compiler.planner._helpers.identity.seed import (
    build_seed_identity as _build_seed_identity,
)


def build_seed_identity(seed: CompiledSeed) -> tuple[str, str]:
    """Return ``(identity_hash, metadata_json)`` for one compiled seed."""

    return _build_seed_identity(seed)
