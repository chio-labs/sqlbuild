"""Loader functions that run declarative ingestr sources."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild._native import SourceEntry, build_ingestr_command
from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.integrations.ingestr._helpers.output import record_ingestr_output
from sqlbuild.integrations.ingestr._helpers.runner import run_ingestr_command
from sqlbuild.integrations.ingestr.exceptions import IngestrIntegrationError
from sqlbuild.integrations.ingestr.models import IngestrCommandResult


def ingestr_loader_function(
    *, source_entry: SourceEntry, name: str
) -> Callable[[LoaderContext], None]:
    """The loader function that runs one declarative ingestr source under `name`."""

    def run(ctx: LoaderContext) -> None:
        command: tuple[str, ...] = build_ingestr_command(
            source_entry=source_entry,
            adapter_name=ctx.adapter.adapter_name,
            connection_config=ctx.connection_config,
            destination_name=ctx.destination_name,
            vars=ctx.vars,
            environment=ctx.target,
            run_id=ctx.run_id,
            is_reload=ctx.is_reload,
        )
        try:
            result: IngestrCommandResult = run_ingestr_command(command)
        except IngestrIntegrationError as error:
            if isinstance(error.run_result, IngestrCommandResult):
                _ = record_ingestr_output(ctx=ctx, result=error.run_result)
            raise
        _ = record_ingestr_output(ctx=ctx, result=result)
        return None

    run.__name__ = name
    return run
