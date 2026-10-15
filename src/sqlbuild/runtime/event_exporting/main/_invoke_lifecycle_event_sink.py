"""Call one lifecycle-event sink on its delivery thread."""

from collections.abc import Callable, Mapping

from sqlbuild.runtime.observability.models import LifecycleEvent


def invoke_lifecycle_event_sink(
    *,
    function: Callable[..., object],
    provider_arguments: Mapping[str, object],
    event: LifecycleEvent,
    completion: Callable[[BaseException | None], None],
) -> None:
    """Call a user sink with one event, then report how the call ended."""

    try:
        _ = function(event=event, **provider_arguments)
    except BaseException as error:
        _ = completion(error)
        return
    _ = completion(None)
