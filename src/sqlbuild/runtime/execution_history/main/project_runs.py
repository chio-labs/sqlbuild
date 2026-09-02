"""Pure run projection entrypoint."""

from collections.abc import Iterable

from sqlbuild.runtime.execution_history._helpers.projection import project_runs as _project_runs
from sqlbuild.runtime.execution_history.models import RunRecord, StoredEvent


def project_runs(
    *, stored_events: Iterable[StoredEvent], current_runs: Iterable[RunRecord] = ()
) -> tuple[RunRecord, ...]:
    """Apply durable event facts in storage order to immutable run projections."""

    return _project_runs(stored_events=stored_events, current_runs=current_runs)
