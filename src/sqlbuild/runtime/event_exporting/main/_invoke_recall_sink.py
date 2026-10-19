"""Call a Recall replacement sink with one record and its writer."""

from collections.abc import Callable, Mapping


def invoke_recall_sink(*, function: Callable[..., object], arguments: Mapping[str, object]) -> bool:
    """Call a user replacement sink and report whether it raised."""

    try:
        _ = function(**arguments)
    except BaseException:
        return True
    return False
