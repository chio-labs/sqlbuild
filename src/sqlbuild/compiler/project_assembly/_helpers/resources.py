"""Materialise the native project assembly result as the objects Python's assembly builds."""

from __future__ import annotations

from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.types import CompileInputsView
from sqlbuild.compiler.project_assembly.constants import (
    COMPILE_INPUT_FAILURE,
    ENVIRONMENT_READ,
    HELD_FAILURE,
    VALUE_FAILURE,
)
from sqlbuild.compiler.project_assembly.models import NativeProjectResources, NativeResourceFailure
from sqlbuild.compiler.project_assembly.types import (
    FailureRow,
    ProjectResourcesRow,
)
from sqlbuild.compiler.sql_analysis.constants import NATIVE_FAILURE_PREFIX


def project_resources(
    *, inputs: CompileInputsView, row: ProjectResourcesRow, held: list[Exception | None]
) -> NativeProjectResources:
    """Return the resource facts the native row describes, in input order, up to the failure."""

    (
        model_deps,
        source_namespaces,
        seed_namespaces,
        function_deps,
        audit_deps,
        reads,
        syntax,
        failure,
    ) = row
    _ = [_replay_read(kind=kind, name=name) for kind, name in reads]
    return NativeProjectResources(
        model_deps=tuple(model_deps),
        model_syntax_valid=tuple(syntax),
        source_namespaces=tuple(source_namespaces),
        seed_namespaces=tuple(seed_namespaces),
        function_deps=tuple(function_deps),
        audit_scope_deps=tuple(audit_deps),
        failure=None if failure is None else _failure(row=failure, held=held),
    )


def _failure(*, row: FailureRow, held: list[Exception | None]) -> NativeResourceFailure:
    slot, index, kind, message, help_text, held_index = row
    error: Exception
    if kind == COMPILE_INPUT_FAILURE:
        error = CompileInputError(message, help=help_text)
    elif kind == VALUE_FAILURE:
        error = ValueError(message)
    elif kind == HELD_FAILURE and held_index is not None and held[held_index] is not None:
        error = cast(Exception, held[held_index])
    else:
        raise _native.NativeCompilerError(
            f"{NATIVE_FAILURE_PREFIX}native project assembly: unknown failure kind '{kind}'"
        )
    return NativeResourceFailure(slot=slot, index=index, error=error)


def _replay_read(*, kind: str, name: str) -> None:
    if kind == ENVIRONMENT_READ:
        COMPILE_INPUT_READS.environment_read(name)
    else:
        COMPILE_INPUT_READS.context_read(name)
