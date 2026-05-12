"""Public dbt compile model ref validation entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.integrations.dbt.helpers.compile_refs import validate_compile_dbt_model_reference
from sqlbuild.integrations.dbt.models import DbtManifestIndex


def validate_compile_model_reference(
    *,
    reference: CompileSqlReference,
    model_relative_path: Path,
    dbt_manifest: DbtManifestIndex | None,
) -> None:
    """Validate a SQLBuild model __dbt_ref() against a dbt manifest."""

    validate_compile_dbt_model_reference(
        reference=reference,
        model_relative_path=model_relative_path,
        dbt_manifest=dbt_manifest,
    )
