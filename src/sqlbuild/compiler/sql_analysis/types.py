"""SQL analysis type-layer declarations."""

from __future__ import annotations

from typing import Protocol


class NativeValidationModule(Protocol):
    """Native schema-validation boundary."""

    def validate_sql_with_schema_json(self, request_json: str) -> str: ...

    def validate_sql_with_schemas_json(self, request_json: str) -> str: ...


class NativeQueryAnalysisModule(Protocol):
    """Native compact query-analysis boundary."""

    def analyze_queries_json(self, request_json: str) -> str: ...

    def analyze_project_queries_json(self, request_json: str) -> str: ...

    def analyze_project_queries_compact_json(self, request_json: str) -> str: ...
