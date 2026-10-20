"""Call one lifecycle-event sink on its long-lived delivery thread."""

from collections.abc import Callable, Mapping
from queue import SimpleQueue

from sqlbuild.runtime.observability.models import LifecycleEvent


def invoke_lifecycle_event_sink(
    *,
    calls: SimpleQueue[
        tuple[Callable[..., object], Mapping[str, object], LifecycleEvent, int] | None
    ],
    results: SimpleQueue[tuple[int, BaseException | None]],
    claims: dict[int, bool],
) -> None:
    """Claim and call the sink with each queued event in order and report how each call ended."""

    for function, provider_arguments, event, token in iter(calls.get, None):
        if not claims.setdefault(token, True):
            del claims[token]
            continue
        try:
            _ = function(event=event, **provider_arguments)
        except BaseException as error:
            results.put((token, error))
        else:
            results.put((token, None))
