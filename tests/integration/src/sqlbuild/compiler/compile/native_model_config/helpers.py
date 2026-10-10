"""Validate one model's effective config with a native model config session."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.attachment.model_config import (
    native_model_config_session,
    native_model_validation,
    native_validation_error,
)
from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    CompileSqlReference,
    ModelResourceNames,
    ModelValidationRequest,
    NativeModelConfigInputs,
    NativeModelConfigSession,
)
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import ProjectConfig

_ACCEPTED: str = "accepted"
_NAMES: ModelResourceNames = ModelResourceNames(
    models={"orders", "customers"},
    seeds={"regions"},
    sources={"raw.orders"},
    functions={"cents", "order_lines"},
    table_functions={"order_lines"},
    custom_materializations=frozenset({"ledger"}),
)


def validation_outcome(*, values: dict[str, object]) -> object:
    """Return `accepted`, or the raised error's shape, for model `orders_daily` reading orders."""

    session: NativeModelConfigSession = native_model_config_session(
        inputs=NativeModelConfigInputs(
            project_config=ProjectConfig(name="orders", adapter="duckdb"),
            target_config=None,
            effective_vars={},
            effective_target_name=None,
            run_id="20261008T000000Z_orders",
            microbatch_concurrency=False,
        ),
        names=_NAMES,
    )
    request: ModelValidationRequest = ModelValidationRequest(
        model_file=DiscoveredSqlModelFile(
            file_path=Path("/project/models/marts/orders_daily.sql"),
            relative_path=Path("models/marts/orders_daily.sql"),
            contents="",
            header_values={},
            header_column_locations={},
            output_column_locations={},
            query_sql="SELECT 1",
        ),
        config=CompileModelConfig(values=values),
        references=(CompileSqlReference(ref_kind=SqlReferenceKind.REF, ref_name="orders"),),
        declared_columns=None,
        query_sql="SELECT 1",
    )
    outcome: _native.NativeConfigError | None = cast(
        _native.NativeConfigError | None,
        native_model_validation(session=session, request=request, rejected=[False]),
    )
    return [
        _ACCEPTED,
        *(
            raised_error_shape(native_validation_error(error=error, values=values))
            for error in filter(None, (outcome,))
        ),
    ][-1]


def header_help(*, purpose: str, entry: str) -> str:
    """Return the help that shows the exact MODEL header entry to add."""

    indent: str = " " * 12
    return (
        f"{purpose}, add this to the MODEL header:\n{indent}MODEL (\n"
        f"{indent}  {entry},\n{indent}  ...\n{indent});"
    )


def raised_error_shape(error: Exception) -> tuple[object, ...]:
    """Return the type, message, code and help of an error."""

    return (
        type(error).__name__,
        str(error),
        getattr(error, "code", None),
        getattr(error, "help", None),
    )
