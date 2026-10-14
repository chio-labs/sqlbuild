"""Resolve a step's flag placeholders against its target model."""

from __future__ import annotations

import duckdb

from scripts.planner_differential._helpers.capturing.state_tables import database_files
from scripts.planner_differential._helpers.steps.relations import schema_and_name
from scripts.planner_differential.models import ModelFacts, PlannerStep, StepContext

_MODEL_PLACEHOLDER: str = "{model}"
_START_PLACEHOLDER: str = "{start_cursor}"
_END_PLACEHOLDER: str = "{end_cursor}"


def step_arguments(
    *, step: PlannerStep, context: StepContext, target: ModelFacts | None
) -> tuple[str, ...] | None:
    """Return the step's plan and build flags, or None when a placeholder has no value."""

    values: dict[str, str] = {}
    if target is not None:
        values[_MODEL_PLACEHOLDER] = target.name
    if any(_START_PLACEHOLDER in argument for argument in step.arguments):
        bounds: tuple[str, str] | None = (
            None if target is None else _cursor_bounds(context=context, target=target)
        )
        if bounds is not None:
            values[_START_PLACEHOLDER], values[_END_PLACEHOLDER] = bounds
    resolved: list[str] = []
    for argument in step.arguments:
        if argument.startswith("{") and argument not in values:
            return None
        resolved.append(values.get(argument, argument))
    return tuple(resolved)


def _cursor_bounds(*, context: StepContext, target: ModelFacts) -> tuple[str, str] | None:
    """The minimum and maximum cursor values the target's relation holds."""

    if target.cursor_column is None:
        return None
    schema, name = schema_and_name(target.qualified_name)
    relation: str = f'"{schema}"."{name}"'
    column: str = f'"{target.cursor_column}"'
    for database in database_files(context.project_dir):
        with duckdb.connect(str(database), read_only=True) as connection:
            try:
                found: tuple[object, ...] | None = connection.execute(
                    f"SELECT CAST(min({column}) AS VARCHAR), CAST(max({column}) AS VARCHAR) "
                    f"FROM {relation}"
                ).fetchone()
            except duckdb.CatalogException:
                continue
        if found is not None and found[0] is not None and found[1] is not None:
            return (str(found[0]), str(found[1]))
    return None
