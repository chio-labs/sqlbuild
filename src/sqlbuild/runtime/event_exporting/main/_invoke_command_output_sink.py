"""Call one command-output sink on its delivery thread."""

from collections.abc import Callable, Mapping

from sqlbuild.runtime.output_capture.models import CommandOutputRecord


def invoke_command_output_sink(
    *,
    function: Callable[..., object],
    provider_arguments: Mapping[str, object],
    record: CommandOutputRecord,
    completion: Callable[[BaseException | None], None],
) -> None:
    """Call a user sink with one output record, then report how the call ended."""

    try:
        _ = function(record=record, **provider_arguments)
    except BaseException as error:
        _ = completion(error)
        return
    _ = completion(None)
