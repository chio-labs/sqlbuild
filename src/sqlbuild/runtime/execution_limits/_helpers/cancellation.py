"""Ask an adapter to cancel a connection's running statement and classify the answer."""

from __future__ import annotations

from typing import Any

from sqlbuild.runtime.execution_limits._helpers.interrupted import interrupted_connections
from sqlbuild.runtime.execution_limits.types import CancellationOutcome


def cancel_connection(*, adapter: Any, connection: Any) -> tuple[CancellationOutcome, str | None]:
    """The cancellation outcome for one connection and a detail when it is not confirmed."""

    adapter_name: str = str(getattr(adapter, "adapter_name", type(adapter).__name__))
    interrupted_connections.mark(connection)
    try:
        requested: bool = bool(adapter.interrupt_connection(connection))
    except Exception as error:
        return CancellationOutcome.FAILED, f"{adapter_name} cancellation failed: {error}"
    if not requested:
        return (
            CancellationOutcome.UNSUPPORTED,
            f"adapter '{adapter_name}' cannot cancel a running statement; the warehouse may "
            "still be running it",
        )
    if getattr(adapter, "statement_cancellation_is_asynchronous", False):
        return (
            CancellationOutcome.UNKNOWN,
            f"cancellation was requested; {adapter_name} stops work asynchronously, so its "
            "final state is not confirmed",
        )
    return CancellationOutcome.CONFIRMED, None
