"""Public dbt compile model ref resolution entrypoint."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.compile_refs import resolve_compile_dbt_ref_references
from sqlbuild.integrations.dbt.models import DbtManifestIndex


def resolve_compile_model_refs(*, query_sql: str, dbt_manifest: DbtManifestIndex | None) -> str:
    """Replace SQLBuild model __dbt_ref() calls with dbt relation names."""

    return resolve_compile_dbt_ref_references(
        query_sql=query_sql,
        dbt_manifest=dbt_manifest,
    )
