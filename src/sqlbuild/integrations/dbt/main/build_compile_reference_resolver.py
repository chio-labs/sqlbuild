"""Build dbt-backed compile-time external reference resolvers."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.manifest.compile_refs import (
    build_compile_external_sql_reference_resolver,
)
from sqlbuild.shared.types import ExternalSqlReferenceResolver


def build_compile_reference_resolver(
    *, manifest_contents: str | None
) -> ExternalSqlReferenceResolver | None:
    """Build a dbt-backed external reference resolver from manifest contents."""

    return build_compile_external_sql_reference_resolver(manifest_contents=manifest_contents)
