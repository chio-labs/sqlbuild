"""Complete batch table freshness results with an outcome for every request."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import TableFreshnessMetadata, TableFreshnessRequest


def complete_table_freshness_results(
    *,
    requests: tuple[TableFreshnessRequest, ...],
    results: dict[TableFreshnessRequest, TableFreshnessMetadata],
    adapter_label: str,
) -> dict[TableFreshnessRequest, TableFreshnessMetadata]:
    """Return one outcome per request; a request without a metadata row is unavailable."""

    completed: dict[TableFreshnessRequest, TableFreshnessMetadata] = dict(results)
    request: TableFreshnessRequest
    for request in requests:
        if request in completed:
            continue
        completed[request] = TableFreshnessMetadata.unavailable(
            message=f"{adapter_label} table freshness metadata not found for {request.name}"
        )
    return completed
