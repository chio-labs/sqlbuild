"""Missing migration origin confirmation for build commands."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.spec.contracts.types import MissingMigrationOriginPolicy


def enforce_missing_migration_origin_policy(
    *,
    plan: PlanOutput,
    allow_missing_migration_origin: bool,
    input_stream: TextIO,
    output_stream: TextIO,
) -> None:
    """Confirm before building past declared migrations whose origin is missing."""

    names: tuple[str, ...] = tuple(
        sorted(
            {
                *(
                    entry.model_name
                    for entry in plan.migration_entries
                    if entry.origin_missing
                    and entry.missing_origin_policy
                    == MissingMigrationOriginPolicy.REQUIRE_CONFIRMATION
                ),
                *(
                    entry.model_name
                    for entry in plan.column_migration_entries
                    if entry.origin_missing
                    and entry.missing_origin_policy
                    == MissingMigrationOriginPolicy.REQUIRE_CONFIRMATION
                ),
            }
        )
    )
    if not names or allow_missing_migration_origin:
        return
    if not input_stream.isatty():
        raise CliUserError(
            f"migrate_from origin is missing for {_names(names)} and "
            "missing_migration_origin requires confirmation",
            code="M102",
            help="Pass --allow-missing-migration-origin to build without migrating them.",
        )
    expected: str = _confirmation_text(names)
    _ = output_stream.write(
        f"The migrate_from origin of {_names(names)} does not exist in this target; nothing "
        "will be migrated.\n\n"
    )
    _ = output_stream.write(f"Type `{expected}` to continue: ")
    output_stream.flush()
    if input_stream.readline().strip() != expected:
        raise CliUserError("build without missing migration origins cancelled", code="M102")


def _confirmation_text(names: tuple[str, ...]) -> str:
    if len(names) == 1:
        return f"build {names[0]} without its migration"
    return f"build {len(names)} models without their migrations"


def _names(names: tuple[str, ...]) -> str:
    return ", ".join(f"'{name}'" for name in names)
