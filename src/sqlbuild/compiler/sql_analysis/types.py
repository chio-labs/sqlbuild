"""SQL analysis type-layer declarations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

type NativeDiagnosticRow = tuple[str, str, int | None, int | None, int | None, int | None, str]
type NativeBindingRequest = tuple[str, list[tuple[str, bool]], dict[str, Mapping[str, str]]]


class NativeProjectCatalog(Protocol):
    def inferred_schema(
        self, *, sql: str, columns: Mapping[str, str], inputs: Mapping[str, Mapping[str, str]]
    ) -> dict[str, str]: ...
    def with_relations(
        self, relations: Mapping[str, Mapping[str, str]]
    ) -> NativeProjectCatalog: ...
    def validation_payload(self, requests: list[NativeBindingRequest]) -> str: ...
    def update_analysis(
        self, relations: Mapping[str, tuple[Mapping[str, str], Mapping[str, str]]]
    ) -> None: ...
    def register_override(self, relations: Mapping[str, Mapping[str, str]]) -> int: ...
    def analyze_compact(self, payload: bytes) -> bytes: ...
    def update_relations(self, relations: Mapping[str, Mapping[str, str]]) -> None: ...
    def binding_results(
        self, requests: list[NativeBindingRequest]
    ) -> list[list[NativeDiagnosticRow]]: ...


class NativeCatalogModule(Protocol):
    def ProjectCatalog(
        self,
        request: dict[str, object],
    ) -> NativeProjectCatalog: ...


class NativeBindingPositions(Protocol):
    def position(
        self, *, start: int | None, line: int | None, column: int | None, message: str
    ) -> tuple[int | None, int | None]: ...


class NativePositionsModule(Protocol):
    def normalize_analysis_sqls(
        self, *, dialect: str, requests: list[tuple[str, dict[str, str]]]
    ) -> list[str]: ...
    def binding_diagnostics(
        self, *, sql: str, dialect: str, rows: list[NativeDiagnosticRow]
    ) -> list[NativeDiagnosticRow]: ...
    def BindingPositions(
        self,
        request: dict[str, object],
    ) -> NativeBindingPositions: ...
    def normalize_analysis_sql(self, request: dict[str, object]) -> str: ...
    def normalize_dialect_sql(self, *, sql: str, dialect: str) -> str: ...


class NativeValidationModule(Protocol):
    """Native schema-validation boundary."""

    def validate_sql_with_schema_json(self, request_json: str) -> str: ...

    def validate_sql_with_schemas_json(self, request_json: str) -> str: ...


class NativeQueryAnalysisModule(Protocol):
    """Native compact query-analysis boundary."""

    def analyze_queries_json(self, request_json: str) -> str: ...

    def analyze_project_queries_json(self, request_json: str) -> str: ...

    def analyze_project_queries_compact_json(self, request_json: str) -> str: ...
