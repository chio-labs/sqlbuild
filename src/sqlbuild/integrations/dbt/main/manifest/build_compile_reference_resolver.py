"""Build dbt-backed compile-time external reference resolvers."""

from __future__ import annotations

from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.integrations.dbt.classes.dbt_compile_reference_resolver import (
    DbtCompileReferenceResolver,
)
from sqlbuild.integrations.dbt.main.manifest.build_compile_manifest_index import (
    build_compile_manifest_index,
)


def build_compile_reference_resolver(
    *, manifest_contents: str | None
) -> ExternalSqlReferenceResolver | None:
    """Build a dbt-backed external reference resolver from manifest contents."""

    if manifest_contents is None:
        return None
    return DbtCompileReferenceResolver(
        dbt_manifest=build_compile_manifest_index(manifest_contents=manifest_contents)
    )
