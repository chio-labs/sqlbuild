"""SQL analysis type-layer declarations."""

from __future__ import annotations

from typing import Protocol


class NativeValidationModule(Protocol):
    """Native schema-validation boundary."""

    def validate_sql_with_schema_json(self, request_json: str) -> str: ...
