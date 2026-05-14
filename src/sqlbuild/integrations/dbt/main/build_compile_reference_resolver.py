"""Build dbt-backed compile-time external reference resolvers."""

from __future__ import annotations

from sqlbuild.integrations.dbt.helpers.compile_refs import (
    build_compile_external_reference_resolver,
)
from sqlbuild.shared.types import ExternalReferenceResolver


def build_compile_reference_resolver(
    *, manifest_contents: str | None
) -> ExternalReferenceResolver | None:
    """Build a dbt-backed external reference resolver from manifest contents."""

    return build_compile_external_reference_resolver(manifest_contents=manifest_contents)
