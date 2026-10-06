"""Read the target of `sqb rename` and `sqb mv` the way `sqb lineage` reads targets."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.lineage.selection import resolve_lineage_target
from sqlbuild.cli.commands.constants import COLUMN_TARGET_KIND, COLUMN_TARGET_SEPARATOR
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import LineageTarget, RefactorCommandRequest
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.refactoring.models import RefactorRequest
from sqlbuild.compiler.refactoring.types import RefactorOperation

_RENAME_USAGE: str = (
    "write the target as <model> or <model>.<column>; the model: and column: prefixes are optional"
)
_MOVE_USAGE: str = "write the target as <model>; the model: prefix is optional"
_RENAME_SCOPE: str = "sqb rename renames models and model columns"
_MOVE_SCOPE: str = "sqb mv moves models"


def refactor_request_for_target(
    *, request: RefactorCommandRequest, all_keys: dict[str, CompiledObjectKey]
) -> RefactorRequest:
    """Read a `sqb rename` or `sqb mv` target the way `sqb lineage` reads its targets."""

    raw: str = request.target.strip()
    target: LineageTarget = resolve_lineage_target(all_keys=all_keys, target=raw)
    is_move: bool = request.command == CliCommand.MV
    _check_target(raw=raw, target=target, is_move=is_move)
    model_name: str = target.name.partition(COLUMN_TARGET_SEPARATOR)[0]
    if is_move:
        return RefactorRequest(
            operation=RefactorOperation.MOVE_MODEL,
            model_name=model_name,
            new_name="",
            destination=request.destination or "",
        )
    new_name: str = (request.new_name or "").strip()
    if target.column_name is None:
        if request.cascade:
            raise CliUserError("--cascade applies to column renames only", code="C954")
        return RefactorRequest(
            operation=RefactorOperation.RENAME_MODEL,
            model_name=model_name,
            new_name=new_name,
        )
    return RefactorRequest(
        operation=RefactorOperation.RENAME_COLUMN,
        model_name=model_name,
        column_name=target.column_name,
        new_name=new_name,
        cascade=request.cascade,
    )


def _check_target(*, raw: str, target: LineageTarget, is_move: bool) -> None:
    verb: str = "move" if is_move else "rename"
    usage: str = _MOVE_USAGE if is_move else _RENAME_USAGE
    key: CompiledObjectKey | None = target.key
    if not target.name or (target.column_name is not None and not target.column_name):
        raise CliUserError(f"cannot {verb} '{raw}'", code="C954", help=usage)
    if key is not None and key.resource_type != CompiledResourceType.MODEL:
        raise CliUserError(
            f"cannot {verb} '{raw}': {key.name} is a {key.resource_type}; "
            f"{_MOVE_SCOPE if is_move else _RENAME_SCOPE}",
            code="C954",
            help=usage,
        )
    if key is not None and not target.kind_matches:
        found: str = (
            f"column: needs <model>.<column>, and {key.name} names a model"
            if target.kind == COLUMN_TARGET_KIND
            else f"{key.name} is a {key.resource_type}, not a {target.kind}"
        )
        raise CliUserError(f"cannot {verb} '{raw}': {found}", code="C954", help=usage)
    if is_move and target.column_name is not None:
        raise CliUserError(
            f"sqb mv moves models; '{raw}' names a column",
            code="C954",
            help=f"rename a column with sqb rename {target.name} <new_name>",
        )
