"""Public Python-node authoring models."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.models import MeasurementThresholds
from sqlbuild.compiler.auditing.types import AuditSeverity
from sqlbuild.errors.contracts.exceptions import SharedInputError
from sqlbuild.python_nodes.types import PythonCheckSeverity, SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceColumnEntry
from sqlbuild.spec.contracts.types import SourceWriteStrategy


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
class AuditFactoryDefinition:
    """Metadata attached to an audit-case factory function."""

    name: str


@dataclass(frozen=True)
class HookDefinition:
    """Metadata attached to a decorated model lifecycle hook function."""

    name: str
    description: str | None = None


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
@dataclass(frozen=True, kw_only=True)
class AuditCase:
    """One named generic-audit attachment generated by an audit factory."""

    name: str
    definition: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    severity: AuditSeverity | None = None
    run_scope: str | None = None
    always_run: bool = False
    description: str | None = None
    thresholds: MeasurementThresholds | None = None
    minimum_samples: int | None = None
    evidence_limit: int | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"^[a-z][a-z0-9_]*$", self.name):
            raise SharedInputError(
                "AuditCase name must be a non-empty lowercase identifier using letters, "
                "numbers, and underscores"
            )
        if not self.definition.strip():
            raise SharedInputError("AuditCase definition must be non-empty")
        if self.minimum_samples is not None and (
            not isinstance(self.minimum_samples, int)
            or isinstance(self.minimum_samples, bool)
            or self.minimum_samples < 0
        ):
            raise SharedInputError("AuditCase minimum_samples must be a non-negative integer")
        if self.evidence_limit is not None and (
            not isinstance(self.evidence_limit, int)
            or isinstance(self.evidence_limit, bool)
            or self.evidence_limit < 0
        ):
            raise SharedInputError("AuditCase evidence_limit must be a non-negative integer")
