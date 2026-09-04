"""Static rejection of capped producers feeding microbatch watermark inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._cursor_roles import resolve_cursor_input_roles
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompileSqlReference,
)
from sqlbuild.compiler.planner._helpers.resolve.lineage import resolve_lineage_reference
from sqlbuild.compiler.planner.main.execution.microbatch_limit import (
    _resolve_microbatch_limit_config,
)
from sqlbuild.compiler.planner.types import IncrementalMode
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.types import MicrobatchLimitAction

_CAP_ACTIONS: frozenset[MicrobatchLimitAction] = frozenset(
    {MicrobatchLimitAction.CAP_FROM_START, MicrobatchLimitAction.CAP_FROM_END}
)


def validate_capped_watermark_inputs(
    *,
    model: CompiledModel,
    models_by_name: dict[str, CompiledModel],
    functions_by_name: dict[str, CompiledFunction] | None = None,
) -> None:
    """Reject capped producers feeding microbatch watermark inputs."""

    if _config_str(model=model, key="incremental_mode") != IncrementalMode.MICROBATCH:
        return
    input_name: str
    for input_name in resolve_cursor_input_roles(model=model).watermark_inputs:
        ref: CompileSqlReference = resolve_lineage_reference(
            model=model,
            input_name=input_name,
            models_by_name=models_by_name,
            functions_by_name=functions_by_name or {},
        )
        producer: CompiledModel | None = _find_capped_producer_ancestor(
            reference=ref,
            models_by_name=models_by_name,
            functions_by_name=functions_by_name or {},
        )
        if producer is None:
            continue
        if producer.name != input_name:
            raise CompileInputError(
                f"model '{model.name}' uses watermark input '{input_name}' derived from capped "
                f"producer '{producer.name}'; capped producers cannot serve as watermark inputs"
            )
        raise CompileInputError(
            f"model '{model.name}' uses capped producer '{producer.name}' as a watermark input; "
            "capped producers cannot serve as watermark inputs"
        )


def _find_capped_producer_ancestor(
    *,
    reference: CompileSqlReference,
    models_by_name: dict[str, CompiledModel],
    functions_by_name: dict[str, CompiledFunction],
) -> CompiledModel | None:
    """Return the first capped microbatch model in a reference's upstream lineage."""

    pending: list[CompileSqlReference] = [reference]
    visited: set[tuple[str, str]] = set()
    while pending:
        current: CompileSqlReference = pending.pop(0)
        identity: tuple[str, str] = (current.ref_kind, current.ref_name)
        if identity in visited:
            continue
        visited.add(identity)
        if current.ref_kind == SqlReferenceKind.REF:
            producer: CompiledModel | None = models_by_name.get(current.ref_name)
            if producer is None:
                continue
            action: MicrobatchLimitAction | None = _resolve_microbatch_limit_config(
                values=producer.config.values
            )[1]
            is_microbatch: bool = (
                _config_str(model=producer, key="incremental_mode") == IncrementalMode.MICROBATCH
            )
            if is_microbatch and action in _CAP_ACTIONS:
                return producer
            if is_microbatch:
                watermark_name: str
                for watermark_name in resolve_cursor_input_roles(model=producer).watermark_inputs:
                    pending.append(
                        resolve_lineage_reference(
                            model=producer,
                            input_name=watermark_name,
                            models_by_name=models_by_name,
                            functions_by_name=functions_by_name,
                        )
                    )
            else:
                pending.extend(producer.references)
        elif current.ref_kind in {
            SqlReferenceKind.UDF,
            SqlReferenceKind.TABLE_FUNCTION,
        }:
            function: CompiledFunction | None = functions_by_name.get(current.ref_name)
            if function is not None:
                pending.extend(function.references)
    return None


def _config_str(*, model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None
