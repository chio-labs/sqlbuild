"""Default full model diff size limits and guard error rendering."""

from __future__ import annotations

import json
import shlex

from sqlbuild.cli.commands.exceptions import DiffSizeGuardError
from sqlbuild.cli.commands.models import DiffCommandRequest
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.diff.exceptions import FullDiffSizeGuardError
from sqlbuild.executor.diff.models import FullDiffModelSize, FullDiffSideSize, FullDiffSizeLimits
from sqlbuild.spec.contracts.constants import DEFAULT_DIFF_MAX_FULL_ROWS
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config

_BOUNDED_WINDOW_PLACEHOLDER: str = "<window>"


def resolve_full_diff_size_limits(
    *,
    request: DiffCommandRequest,
    discovered_inputs: DiscoveredProjectInputs,
    from_target: str,
    to_target: str,
) -> FullDiffSizeLimits | None:
    """Return per-side row limits when no explicit comparison mode was requested."""

    if request.full or request.schema_only or request.bounded is not None:
        return None
    return FullDiffSizeLimits(
        left_target=from_target,
        right_target=to_target,
        left_max_rows=_target_max_full_rows(
            discovered_inputs=discovered_inputs, target_name=from_target
        ),
        right_max_rows=_target_max_full_rows(
            discovered_inputs=discovered_inputs, target_name=to_target
        ),
    )


def build_diff_size_guard_error(
    *,
    request: DiffCommandRequest,
    from_target: str,
    to_target: str,
    error: FullDiffSizeGuardError,
) -> DiffSizeGuardError:
    """Describe every blocked model and the explicit commands that replace the guarded run."""

    commands: dict[str, str | None] = _replacement_commands(
        request=request,
        from_target=from_target,
        to_target=to_target,
        blocked=error.blocked,
    )
    lines: list[str] = [error.message]
    model: FullDiffModelSize
    for model in error.blocked:
        lines.append(
            f"  {model.name}: {_side_text(model.left)}; {_side_text(model.right)}"
            + ("" if model.has_cursor else "; no cursor")
        )
    lines.append("Run one of these instead:")
    lines.append(f"  {commands['full']}")
    if commands["bounded"] is not None:
        lines.append(f"  {commands['bounded']}")
    lines.append(f"  {commands['schema_only']}")
    over_targets: tuple[str, ...] = _over_limit_targets(blocked=error.blocked)
    bounded_help: str = (
        ""
        if commands["bounded"] is None
        else ", --bounded compares a recent cursor window "
        f"(replace {_BOUNDED_WINDOW_PLACEHOLDER} with a duration such as 7d)"
    )
    return DiffSizeGuardError(
        "\n".join(lines),
        code="C270",
        help=(
            f"--full compares every row{bounded_help}, and --schema-only compares columns "
            "only; or raise "
            + " and ".join(f"targets.{target}.diff.max_full_rows" for target in over_targets)
        ),
        details={
            "from_target": from_target,
            "to_target": to_target,
            "models": [_model_payload(model) for model in error.blocked],
            "commands": commands,
        },
    )


def _over_limit_targets(*, blocked: tuple[FullDiffModelSize, ...]) -> tuple[str, ...]:
    targets: dict[str, None] = {}
    model: FullDiffModelSize
    for model in blocked:
        side: FullDiffSideSize
        for side in (model.left, model.right):
            if side.exceeds_limit:
                targets[side.target] = None
    return tuple(targets)


def _target_max_full_rows(
    *, discovered_inputs: DiscoveredProjectInputs, target_name: str
) -> int | None:
    configured: int | str | None = resolve_target_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_name=target_name,
    ).diff.max_full_rows
    if configured is None:
        return DEFAULT_DIFF_MAX_FULL_ROWS
    return configured if isinstance(configured, int) else None


def _side_text(side: FullDiffSideSize) -> str:
    limit: str = "unlimited" if side.max_rows is None else f"{side.max_rows:,}"
    if side.row_count is None:
        size: str = "size unknown" if side.detail is None else f"size unknown: {side.detail}"
    else:
        size = f"{side.row_count:,} rows"
    return f"{side.target} {size}, limit {limit}"


def _model_payload(model: FullDiffModelSize) -> dict[str, object]:
    return {
        "name": model.name,
        "has_cursor": model.has_cursor,
        "from": _side_payload(model.left),
        "to": _side_payload(model.right),
    }


def _side_payload(side: FullDiffSideSize) -> dict[str, object]:
    return {
        "target": side.target,
        "relation": side.relation,
        "row_count": side.row_count,
        "max_full_rows": side.max_rows,
        "exceeds_limit": side.exceeds_limit,
        "detail": side.detail,
    }


def _replacement_commands(
    *,
    request: DiffCommandRequest,
    from_target: str,
    to_target: str,
    blocked: tuple[FullDiffModelSize, ...],
) -> dict[str, str | None]:
    scope: tuple[str, ...] = _scope_arguments(request=request)
    project: tuple[str, ...] = (
        () if request.project_dir is None else ("--project-dir", str(request.project_dir))
    )
    prefix: tuple[str, ...] = ("sqb", *project, "diff", f"{from_target}:{to_target}")
    bounded_available: bool = all(model.has_cursor for model in blocked)
    return {
        "full": _join((*prefix, "--full", *scope)),
        "bounded": (
            _join((*prefix, "--bounded", _BOUNDED_WINDOW_PLACEHOLDER, *scope))
            if bounded_available
            else None
        ),
        "schema_only": _join((*prefix, "--schema-only", *scope)),
    }


def _scope_arguments(*, request: DiffCommandRequest) -> tuple[str, ...]:
    arguments: list[str] = []
    if request.select:
        arguments.extend(("--select", *request.select))
    if request.exclude:
        arguments.extend(("--exclude", *request.exclude))
    if request.unique_key_override:
        arguments.extend(("--key", *request.unique_key_override))
    if request.unkeyed:
        arguments.append("--unkeyed")
    if request.excluded_columns_override:
        arguments.extend(("--exclude-column", *request.excluded_columns_override))
    tolerance: str
    for tolerance in request.tolerance_overrides:
        arguments.extend(("--tolerance", tolerance))
    if request.cli_vars:
        arguments.extend(("--vars", json.dumps(request.cli_vars, sort_keys=True)))
    return tuple(arguments)


def _join(parts: tuple[str, ...]) -> str:
    return " ".join(
        part if part == _BOUNDED_WINDOW_PLACEHOLDER else shlex.quote(part) for part in parts
    )
