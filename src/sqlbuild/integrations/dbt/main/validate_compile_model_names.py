"""Public dbt compile duplicate model-name validation entrypoint."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.manifest.compile_refs import validate_compile_dbt_model_names
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex


def validate_compile_model_names(
    *, known_model_names: set[str], dbt_manifest: DbtManifestIndex | None
) -> None:
    """Reject dbt/SQLBuild duplicate logical model names."""

    validate_compile_dbt_model_names(
        known_model_names=known_model_names,
        dbt_manifest=dbt_manifest,
    )
