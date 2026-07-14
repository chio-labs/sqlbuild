"""Compile-time dbt ref helpers used by SQLBuild model attachment."""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models.core import CompileSqlReference
from sqlbuild.compiler.references.main.reference_call_prefix_pattern_text import (
    reference_call_prefix_pattern_text,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.integrations.dbt._helpers.manifest.core import (
    build_dbt_manifest_index,
    resolve_dbt_manifest_model,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex

_DBT_REF_PATTERN: re.Pattern[str] = re.compile(
    rf'{reference_call_prefix_pattern_text(SqlReferenceKind.DBT_REF)}\s*"([^"]+)"\s*'
    r'(?:,\s*"([^"]+)"\s*)?\)'
)


def build_compile_dbt_manifest_index(*, manifest_contents: str | None) -> DbtManifestIndex | None:
    """Build a dbt manifest index from discovered manifest contents."""

    if manifest_contents is None:
        return None
    try:
        raw_data: object = json.loads(manifest_contents)
    except json.JSONDecodeError as exc:
        raise CompileInputError(
            f"Invalid dbt manifest JSON: {exc.msg}",
            code="C211",
        ) from exc
    return build_dbt_manifest_index(raw_data=raw_data)


def validate_compile_dbt_model_names(
    *, known_model_names: set[str], dbt_manifest: DbtManifestIndex | None
) -> None:
    """Reject ambiguous ownership between dbt and SQLBuild models."""

    if dbt_manifest is None:
        return
    duplicate_names: tuple[str, ...] = tuple(
        sorted(name for name in known_model_names if name in dbt_manifest.models_by_name)
    )
    if duplicate_names:
        raise CompileInputError(
            f"dbt and SQLBuild models share names: {', '.join(duplicate_names)}",
            code="C215",
            help=(
                "Rename either the dbt model or SQLBuild model; owner-qualified names "
                "are not supported."
            ),
        )


def validate_compile_dbt_model_reference(
    *,
    reference: CompileSqlReference,
    model_relative_path: Path,
    dbt_manifest: DbtManifestIndex | None,
) -> None:
    """Validate one compile-time dbt ref against a dbt manifest."""

    if reference.ref_kind != SqlReferenceKind.DBT_REF:
        return
    if dbt_manifest is None:
        raise CompileInputError(
            f"Model file {model_relative_path} uses "
            f"{SqlReferenceKind.DBT_REF.example_call(reference.ref_name)} but no dbt "
            "manifest was found",
            code="C214",
            help=(
                "Run dbt compile or configure dbt target_path so SQLBuild can read manifest.json."
            ),
        )
    resolve_dbt_manifest_model(
        manifest=dbt_manifest,
        package_name=reference.ref_package,
        name=reference.ref_name,
    )


def resolve_compile_dbt_ref_references(
    *, query_sql: str, dbt_manifest: DbtManifestIndex | None
) -> str:
    """Replace model __dbt_ref() calls with dbt manifest relation names."""

    if dbt_manifest is None:
        return query_sql

    def _replace_dbt_ref(match: re.Match[str]) -> str:
        first_arg: str = match.group(1)
        second_arg: str | None = match.group(2)
        return resolve_dbt_manifest_model(
            manifest=dbt_manifest,
            package_name=first_arg if second_arg is not None else None,
            name=second_arg if second_arg is not None else first_arg,
        ).relation_name

    return _DBT_REF_PATTERN.sub(_replace_dbt_ref, query_sql)
