"""Optional adapter retention capability."""

from __future__ import annotations

from typing import Any, ClassVar

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import (
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

    def render_retention_changes(
        self, *, request: RetentionRequest
    ) -> tuple[RenderedRetentionChange, ...]:
        del request
        raise AdapterUserError(
            message=f"adapter '{self.adapter_name}' does not support retention changes"
        )
