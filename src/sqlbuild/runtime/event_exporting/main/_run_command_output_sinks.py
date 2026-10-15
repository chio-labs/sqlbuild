"""Call command-output sinks on their dispatcher's single delivery thread."""

from collections.abc import Callable, Mapping
from queue import SimpleQueue

from sqlbuild.runtime.output_capture.models import CommandOutputRecord


def run_command_output_sinks(
    *,
    calls: SimpleQueue[
        tuple[Callable[..., object], Mapping[str, object], CommandOutputRecord, SimpleQueue[bool]]
        | None
    ],
) -> None:
    """Call each queued user sink in order, reporting whether it raised, until `None` arrives."""

    for function, provider_arguments, record, outcome in iter(calls.get, None):
        try:
            _ = function(record=record, **provider_arguments)
        except BaseException:
            outcome.put(True)
        else:
            outcome.put(False)
