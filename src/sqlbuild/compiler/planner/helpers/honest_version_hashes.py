"""Build standard model write hashes from actually available upstream identities."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.main.version_identity_version_hash import (
    build_model_version_identity_hash,
)
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    PlannerChangeResults,
    PlannerScope,
    StandardModelVersionIdentities,
    WarehouseSnapshot,
)


def with_honest_model_write_hashes(
    *,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    changes: PlannerChangeResults,
    version_identities: StandardModelVersionIdentities,
    available_model_hashes: dict[str, str] | None = None,
) -> PlannerChangeResults:
    """Replace planned write hashes with hashes based on upstreams available this run."""

    write_hashes: dict[str, str] = {
        **version_identities.function_local_hashes,
        **_seed_write_hashes(scope=scope, snapshot=snapshot, version_identities=version_identities),
        **_built_model_hashes(snapshot),
        **(available_model_hashes or {}),
    }
    models_by_name: dict[str, CompiledModel] = scope.models_by_name
    model_changes: dict[str, ChangeDetectionResult] = dict(changes.models)
    key: CompiledObjectKey
    for key in scope.execution_order:
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        model: CompiledModel | None = models_by_name.get(key.name)
        if model is None:
            continue
        if key not in scope.selected_keys:
            continue
        local_hash: str | None = version_identities.model_local_hashes.get(model.name)
        if local_hash is None:
            continue
        write_hash: str = build_model_version_identity_hash(
            local_hash=local_hash,
            upstream_deps=model.deps,
            upstream_version_hashes=write_hashes,
            source_version_hashes={},
        )
        write_hashes[model.name] = write_hash
        change: ChangeDetectionResult | None = model_changes.get(model.name)
        if change is None:
            continue
        model_changes[model.name] = replace(change, fingerprint_version_hash=write_hash)
    return replace(changes, models=model_changes)


def _seed_write_hashes(
    *,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    version_identities: StandardModelVersionIdentities,
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    seed_name: str
    expected_hash: str
    for seed_name, expected_hash in version_identities.seed_version_hashes.items():
        seed_key: CompiledObjectKey = CompiledObjectKey(
            resource_type=CompiledResourceType.SEED, name=seed_name
        )
        if seed_key in scope.selected_keys:
            hashes[seed_name] = expected_hash
            continue
        fingerprint: Fingerprint | None = snapshot.fingerprints.seeds.get(seed_name)
        hashes[seed_name] = fingerprint.version_hash if fingerprint is not None else expected_hash
    return hashes


def _built_model_hashes(snapshot: WarehouseSnapshot) -> dict[str, str]:
    return {
        model_name: fingerprint.version_hash
        for model_name, fingerprint in snapshot.fingerprints.models.items()
        if fingerprint.version_hash
    }
