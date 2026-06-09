"""Direct planner model version identity helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledFunction, CompiledModel
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.main.version_identity_function_hashes import (
    build_function_local_hashes,
)
from sqlbuild.compiler.planner.main.version_identity_local_hash import (
    build_model_local_identity_hash,
)
from sqlbuild.compiler.planner.main.version_identity_model_metadata import (
    build_model_version_identity_metadata_json,
)
from sqlbuild.compiler.planner.main.version_identity_version_hash import (
    build_model_version_identity_hash,
)
from sqlbuild.compiler.planner.models import DirectModelVersionIdentities, PlannerScope


def build_direct_model_version_identities(
    *,
    functions: tuple[CompiledFunction, ...],
    scope: PlannerScope,
    source_version_hashes: dict[str, str] | None = None,
) -> DirectModelVersionIdentities:
    """Compute current direct model identities from code and upstream identities."""

    function_local_hashes: dict[str, str] = build_function_local_hashes(functions=functions)
    model_metadata_jsons: dict[str, str] = {}
    model_local_hashes: dict[str, str] = {}
    model_version_hashes: dict[str, str] = dict(function_local_hashes)
    source_hashes: dict[str, str] = source_version_hashes or {}

    key: object
    for key in scope.execution_order:
        if not hasattr(key, "resource_type") or key.resource_type != CompiledResourceType.MODEL:
            continue
        model: CompiledModel | None = scope.models_by_name.get(key.name)
        if model is None:
            continue
        metadata_json: str = build_model_version_identity_metadata_json(
            model=model,
            function_local_hashes=function_local_hashes,
        )
        model_metadata_jsons[model.name] = metadata_json
        local_hash: str = build_model_local_identity_hash(
            query_sql=model.query_sql,
            metadata_json=metadata_json,
        )
        model_local_hashes[model.name] = local_hash
        model_version_hashes[model.name] = build_model_version_identity_hash(
            local_hash=local_hash,
            upstream_deps=model.deps,
            upstream_version_hashes=model_version_hashes,
            source_version_hashes=source_hashes,
        )

    return DirectModelVersionIdentities(
        function_local_hashes=function_local_hashes,
        model_metadata_jsons=model_metadata_jsons,
        model_local_hashes=model_local_hashes,
        model_version_hashes=model_version_hashes,
    )
