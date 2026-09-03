"""Frozen cases for execution history conformance tests."""

from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.execution_history import EventFilter, EventLogStorage, RunStorage
from sqlbuild.runtime.observability.types import JSONValue


@dataclass(frozen=True)
class BackendCase:
    description: str
    event_log_factory: Callable[[], EventLogStorage]
    run_storage_factory: Callable[[], RunStorage]
    append_failing_event_log_factory: Callable[[], EventLogStorage]
    project_failing_run_storage_factory: Callable[[], RunStorage]
    atomic_failing_run_storage_factory: Callable[[], RunStorage]
    project_call_count: Callable[[RunStorage], int]
    expected_backend: str


@dataclass(frozen=True)
class ContractCase:
    description: str
    expected_count: int


@dataclass(frozen=True)
class PagingCase:
    description: str
    page_size: int
    expected_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class FilterCase:
    description: str
    event_filter: EventFilter
    expected_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProjectionCase:
    description: str
    expected_status: str
    expected_complete: bool


@dataclass(frozen=True)
class LimitCase:
    description: str
    limit: object
    expected_error: str


@dataclass(frozen=True)
class SchemaVersionCase:
    description: str
    target_version: int
    expected_error: str


@dataclass(frozen=True)
class FilterValidationCase:
    description: str
    filter_factory: Callable[[], object]
    expected_error: str


@dataclass(frozen=True)
class OpaqueIdCase:
    description: str
    event_id: JSONValue
    expected_error: str
