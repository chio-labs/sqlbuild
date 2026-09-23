"""Optional adapter retention capability."""

from __future__ import annotations

from typing import Any, ClassVar

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import (
    RelationInfo,
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)


class RetentionAdapterMixin:
    """Provide explicit unsupported defaults for warehouse retention operations."""

    adapter_name: ClassVar[str]

    def inspect_retention(self, *, connection: Any, request: RetentionRequest) -> RetentionState:
        del connection, request
        raise AdapterUserError(
            message=f"adapter '{self.adapter_name}' does not support retention inspection"
        )

    def inspect_retentions(
        self, *, connection: Any, requests: tuple[RetentionRequest, ...]
    ) -> dict[str, RetentionState]:
        """Inspect several requests; adapters may override with a batched implementation."""

        return {
            request.request_id: self.inspect_retention(connection=connection, request=request)
            for request in requests
        }

    def retention_state_from_relation(
        self, *, request: RetentionRequest, relation: RelationInfo
    ) -> RetentionState | None:
        """Return retention state already carried by a listed relation, when available."""

        del request, relation
        return None

    def render_retention_changes(
        self, *, request: RetentionRequest, state: RetentionState | None = None
    ) -> tuple[RenderedRetentionChange, ...]:
        del request, state
        raise AdapterUserError(
            message=f"adapter '{self.adapter_name}' does not support retention changes"
        )
