"""Build dbt-backed compile-time external reference resolvers."""

from __future__ import annotations

from sqlbuild._native import build_compile_dbt_manifest_index
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.integrations.dbt.classes.dbt_compile_reference_resolver import (
    DbtCompileReferenceResolver,
)


def build_compile_reference_resolver(
    *, manifest_contents: str | None
) -> ExternalSqlReferenceResolver | None:
    """Build a dbt-backed external reference resolver from manifest contents."""

    if manifest_contents is None:
        return None
    return DbtCompileReferenceResolver(
        dbt_manifest=build_compile_dbt_manifest_index(manifest_contents=manifest_contents)
    )
