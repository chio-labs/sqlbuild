"""Hand audit, SQL test and SQL hook SQL to the native resource SQL checks."""

from __future__ import annotations

from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import CompiledProjectView


def get_resource_sql_diagnostics(
    *,
    project: CompiledProjectView,
    shapes: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
) -> tuple[CompilerDiagnostic, ...]:
    """Bind audits, SQL tests and SQL hooks against the same closed shapes as models."""

    return _native.resource_sql_diagnostics_of(
        cast(Any, project.binding_catalog).native, project, shapes, profile
    )
