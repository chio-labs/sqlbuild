"""Reject cursor-based incremental models that have no input to bound their cursor window."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.constants import (
    CURSOR_INPUTS_CONFIG_KEY,
    CURSOR_MODEL_WITHOUT_INPUTS_CODE,
)
from sqlbuild.compiler.compile.models import CompileModelInput, CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.main._model_header_entry_span import get_model_header_entry_span
from sqlbuild.compiler.planner.types import MaterializationType, MicrobatchStrategy
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.models import SourceLocation

_CURSOR_CONFIG_KEY: str = "cursor"
_RELATION_REFERENCE_KINDS: frozenset[SqlReferenceKind] = frozenset(
    {
        SqlReferenceKind.REF,
        SqlReferenceKind.SOURCE,
        SqlReferenceKind.SEED,
        SqlReferenceKind.DBT_REF,
    }
)
_HELP: str = (
    "read the data through __ref(), __source() or __seed() so its cursor can bound the window, "
    "or use materialized table if the model has no upstream data"
)


def cursor_model_without_inputs_diagnostics(
    *, model_inputs: tuple[CompileModelInput, ...]
) -> tuple[CompilerDiagnostic, ...]:
    """Return one error per cursor-based incremental model with no cursor inputs."""

    return tuple(
        _diagnostic(model_input)
        for model_input in model_inputs
        if _lacks_cursor_inputs(model_input)
    )


def _lacks_cursor_inputs(model_input: CompileModelInput) -> bool:
    values: dict[str, object] = model_input.config.values
    if get_config_str(values=values, key="materialized") != MaterializationType.INCREMENTAL:
        return False
    if get_config_str(values=values, key=_CURSOR_CONFIG_KEY) is None:
        return False
    if (
        get_config_str(values=values, key="microbatch_strategy")
        == MicrobatchStrategy.ROLLING_WINDOW
    ):
        return False
    if values.get(CURSOR_INPUTS_CONFIG_KEY) is not None:
        return False
    return not any(
        reference.ref_kind in _RELATION_REFERENCE_KINDS for reference in model_input.references
    )


def _diagnostic(model_input: CompileModelInput) -> CompilerDiagnostic:
    name: str = model_input.model_file.file_path.stem
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=CURSOR_MODEL_WITHOUT_INPUTS_CODE,
        message=(
            f"incremental model '{name}' reads no inputs, so builds after the first "
            "cannot work out their cursor window"
        ),
        resource_type=CompiledResourceType.MODEL,
        resource_name=name,
        location=_cursor_location(
            path=model_input.model_file.relative_path,
            contents=model_input.model_file.contents,
        ),
        help=_HELP,
    )


def _cursor_location(*, path: Path, contents: str) -> SourceLocation:
    span: tuple[int, int] | None = get_model_header_entry_span(
        contents=contents, key=_CURSOR_CONFIG_KEY
    )
    start: int = 0 if span is None else span[0]
    line: int = contents.count("\n", 0, start) + 1
    column: int = start - (contents.rfind("\n", 0, start) + 1) + 1
    if span is None:
        return SourceLocation(path=path, line=line, column=column)
    return SourceLocation(
        path=path,
        line=line,
        column=column,
        end_line=line,
        end_column=column + span[1] - span[0],
    )
