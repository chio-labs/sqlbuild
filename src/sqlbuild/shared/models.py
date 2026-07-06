from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.shared.constants import DEFAULT_MAX_DISPLAY_ENTRIES
from sqlbuild.shared.exceptions.errors import SharedInputError
from sqlbuild.shared.types import (
    LocalNodePlanAction,
    LocalNodePlanReason,
    PythonCheckSeverity,
    SqlResourceRefKind,
)
from sqlbuild.spec.models.source import SourceColumnEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


@dataclass(frozen=True)
class RelationLookup:
    """Existing warehouse relations gathered once, queried by schema and name in memory."""

    relations_by_key: dict[tuple[str | None, str | None, str], RelationInfo]

    @staticmethod
    def key(
        *, database: str | None = None, schema: str | None, name: str
    ) -> tuple[str | None, str | None, str]:
        """Build the case-insensitive lookup key for one relation."""

        return (
            None if database is None else database.lower(),
            None if schema is None else schema.lower(),
            name.lower(),
        )

    def get(
        self, *, database: str | None = None, schema: str | None, name: str
    ) -> RelationInfo | None:
        """Return the gathered relation at one schema and name, or None when absent."""

        return self.relations_by_key.get(self.key(database=database, schema=schema, name=name))

    def exists(self, *, database: str | None = None, schema: str | None, name: str) -> bool:
        """Return whether a relation was present at one schema and name."""

        return self.key(database=database, schema=schema, name=name) in self.relations_by_key

    def is_transient(self, *, database: str | None = None, schema: str | None, name: str) -> bool:
        """Return whether a relation is transient, defaulting to False when absent or unknown."""

        relation: RelationInfo | None = self.get(database=database, schema=schema, name=name)
        return bool(relation.is_transient) if relation is not None else False


@dataclass(frozen=True)
class SelectorExpansion:
    """One selector token split into graph expansion flags and core selector text."""

    core: str
    upstream: bool = False
    downstream: bool = False


@dataclass(frozen=True)
class PrephaseProgressRow:
    """One prephase result row for shared runtime output."""

    label: str
    name: str
    status: str
    duration_seconds: float | None = None
    caused_by_names: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class LocalNodePlanInput:
    """Local state needed to classify one graph node before propagation."""

    fingerprint_exists: bool
    relation_exists: bool
    full_refresh: bool = False
    local_hash: str | None = None
    previous_hash: str | None = None


@dataclass(frozen=True)
class LocalNodePlanOutcome:
    """Neutral local action and reason for one graph node."""

    action: LocalNodePlanAction
    reason: LocalNodePlanReason


@dataclass(frozen=True)
class DisplayOptions:
    """Options controlling bounded human output."""

    max_entries_per_section: int | None = DEFAULT_MAX_DISPLAY_ENTRIES
    overflow_flag: str = "--verbose"


@dataclass(frozen=True)
class TextStyle:
    """One ANSI style role in the CLI theme."""

    prefix: str
    suffix: str = "\033[0m"

    def apply(self, text: str, *, use_color: bool) -> str:
        """Apply this style when color is enabled."""

        if not use_color or not self.prefix:
            return text
        return f"{self.prefix}{text}{self.suffix}"


@dataclass(frozen=True)
class CliTheme:
    """Semantic style roles for human CLI output."""

    title: TextStyle
    section: TextStyle
    label: TextStyle
    value: TextStyle
    accent: TextStyle
    plan_section: TextStyle
    object_name: TextStyle
    command: TextStyle
    success: TextStyle
    success_strong: TextStyle
    warning: TextStyle
    warning_strong: TextStyle
    error: TextStyle
    error_strong: TextStyle
    error_muted: TextStyle
    log_label: TextStyle
    skipped: TextStyle
    muted: TextStyle
    dbt_section: TextStyle
    dbt_label: TextStyle
    dbt_object_name: TextStyle
    dbt_execution_label: TextStyle


@dataclass(frozen=True)
class DiscoveredAdapter:
    """A discovered project-local adapter class."""

    adapter_name: str
    adapter_class: type[StrictAdapter]
    file_path: Path


@dataclass(frozen=True)
class LoaderDefinition:
    """Metadata attached to a decorated source loader function."""

    name: str
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...] = ()
    destination: str | None = None
    write_strategy: SourceWriteStrategy | None = None
    cursor_column: str | None = None
    unique_key: tuple[str, ...] = ()
    columns: tuple[SourceColumnEntry, ...] = ()
    contract: str | None = None


@dataclass(frozen=True)
class FactoryDefinition:
    """Metadata attached to a Python-node factory function."""

    name: str


@dataclass(frozen=True)
class SqlHookEntry:
    """A model lifecycle hook that executes SQL."""

    statement: str


@dataclass(frozen=True)
class PythonHookEntry:
    """A model lifecycle hook that invokes a discovered Python hook."""

    name: str
    kwargs: dict[str, object]


@dataclass(frozen=True)
class HookDefinition:
    """Metadata attached to a decorated model lifecycle hook function."""

    name: str
    description: str | None = None


@dataclass(frozen=True)
class SqlResourceRef:
    """Typed dependency reference to a SQLBuild SQL graph resource."""

    kind: SqlResourceRefKind
    name: str


@dataclass(frozen=True)
class ColumnLineageRef:
    """Graph-based upstream column reference for declared Python-node lineage."""

    node: str
    column: str


@dataclass(frozen=True, init=False)
class RetryPolicy:
    """Retry policy metadata for Python-node execution."""

    max_attempts: int
    retry_on: tuple[type[BaseException], ...]
    initial_delay_seconds: float
    backoff_multiplier: float
    max_delay_seconds: float | None
    max_elapsed_seconds: float | None
    jitter: bool

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        retry_on: type[BaseException]
        | tuple[type[BaseException], ...]
        | list[type[BaseException]] = Exception,
        initial_delay_seconds: float = 1.0,
        backoff_multiplier: float = 2.0,
        max_delay_seconds: float | None = 30.0,
        max_elapsed_seconds: float | None = None,
        jitter: bool = True,
    ) -> None:
        if max_attempts < 1:
            raise SharedInputError("RetryPolicy max_attempts must be at least 1")
        if initial_delay_seconds < 0:
            raise SharedInputError("RetryPolicy initial_delay_seconds must be non-negative")
        if backoff_multiplier < 1:
            raise SharedInputError("RetryPolicy backoff_multiplier must be at least 1")
        if max_delay_seconds is not None and max_delay_seconds < 0:
            raise SharedInputError("RetryPolicy max_delay_seconds must be non-negative")
        if max_elapsed_seconds is not None and max_elapsed_seconds < 0:
            raise SharedInputError("RetryPolicy max_elapsed_seconds must be non-negative")
        normalized_retry_on: tuple[type[BaseException], ...]
        if isinstance(retry_on, type) and issubclass(retry_on, BaseException):
            normalized_retry_on = (retry_on,)
        else:
            normalized_retry_on = tuple(retry_on)
            exception_type: type[BaseException]
            for exception_type in normalized_retry_on:
                if not isinstance(exception_type, type) or not issubclass(
                    exception_type, BaseException
                ):
                    raise SharedInputError("RetryPolicy retry_on must contain exception classes")
        object.__setattr__(self, "max_attempts", max_attempts)
        object.__setattr__(self, "retry_on", normalized_retry_on)
        object.__setattr__(self, "initial_delay_seconds", initial_delay_seconds)
        object.__setattr__(self, "backoff_multiplier", backoff_multiplier)
        object.__setattr__(self, "max_delay_seconds", max_delay_seconds)
        object.__setattr__(self, "max_elapsed_seconds", max_elapsed_seconds)
        object.__setattr__(self, "jitter", jitter)


@dataclass(frozen=True)
class TaskDefinition:
    """Metadata attached to a decorated SQLBuild task function."""

    name: str
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...] = ()
    tags: tuple[str, ...] = ()
    group: str | None = None
    description: str | None = None
    meta: dict[str, object] | None = None
    retry: RetryPolicy | None = None


@dataclass(frozen=True)
class AssetDefinition:
    """Metadata attached to a decorated SQLBuild asset function."""

    name: str
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...] = ()
    tags: tuple[str, ...] = ()
    group: str | None = None
    description: str | None = None
    meta: dict[str, object] | None = None
    columns: tuple[SourceColumnEntry, ...] = ()
    column_lineage: dict[str, tuple[ColumnLineageRef, ...]] | None = None
    retry: RetryPolicy | None = None


@dataclass(frozen=True)
class CheckDefinition:
    """Metadata attached to a decorated SQLBuild check function."""

    name: str
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...]
    severity: PythonCheckSeverity = PythonCheckSeverity.ERROR
    tags: tuple[str, ...] = ()
    group: str | None = None
    description: str | None = None
    meta: dict[str, object] | None = None


@dataclass(frozen=True)
class ParsedScenarioArtifactName:
    """Parsed physical name for one scenario-owned artifact."""

    hash_prefix: str
    kind: str
    logical_name: str


@dataclass(frozen=True)
class ConnectionHooks:
    """Progress and connection lifecycle callbacks for long-running operations."""

    on_progress: Callable[[str], None] | None = None
    on_connection_start: Callable[[int], None] | None = None
    on_connection_complete: Callable[[int, float], None] | None = None
    on_connection_error: Callable[[int, float], None] | None = None


@dataclass(frozen=True)
class CursorWindow:
    """Resolved cursor bounds for one execution run."""

    start_cursor_ts: datetime | None = None
    end_cursor_ts: datetime | None = None
    start_cursor_int: int | None = None
    end_cursor_int: int | None = None
