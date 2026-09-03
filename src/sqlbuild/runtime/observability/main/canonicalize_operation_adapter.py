"""Canonical operation adapter identity."""

from sqlbuild.runtime.observability.constants import OPERATION_ADAPTERS
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError


def canonicalize_operation_adapter(adapter_name: object) -> str:
    """Return a bounded built-in adapter identity without leaking custom names."""

    if adapter_name is None or (isinstance(adapter_name, str) and not adapter_name):
        raise ObservabilityValidationError("adapter_name must be a non-empty string")
    if isinstance(adapter_name, str) and adapter_name in OPERATION_ADAPTERS - {"custom"}:
        return adapter_name
    return "custom"
