"""Resolve a dbt reference relation."""

from sqlbuild.integrations.dbt.helpers.manifest.sqlbuild_refs import (
    resolve_dbt_reference_relation as _resolve,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex


def resolve_dbt_reference_relation(
    *,
    manifest: DbtManifestIndex | None,
    ref_kind: str,
    ref_name: str,
    ref_package: str | None,
) -> str | None:
    """Resolve one external dbt reference to its relation."""

    return _resolve(
        manifest=manifest,
        ref_kind=ref_kind,
        ref_name=ref_name,
        ref_package=ref_package,
    )
