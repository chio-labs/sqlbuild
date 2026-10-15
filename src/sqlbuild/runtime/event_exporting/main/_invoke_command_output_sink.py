"""Call one command-output sink."""

from collections.abc import Callable, Mapping

from sqlbuild.runtime.output_capture.models import CommandOutputRecord


def invoke_command_output_sink(
    *,
    function: Callable[..., object],
    provider_arguments: Mapping[str, object],
    record: CommandOutputRecord,
) -> None:
    """Call a user sink with one output record and its bound provider instances."""

    _ = function(record=record, **provider_arguments)
