"""Dataclass-backed scope unit test cases."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.scopes.models import DeclarationIdentity, ResourceIdentity
from sqlbuild.compiler.scopes.types import (
    InaccessibleReason,
    ResourceKind,
    ScopeDiagnosticCode,
    ScopeKind,
    VisibilityReason,
)


@dataclass(frozen=True)
class PathNormalizationCase:
    """One project-relative path normalization case."""

    description: str
    path: str
    expected_path: str


@dataclass(frozen=True)
class PathVisibilityCase:
    """One component-aware lexical visibility case."""

    description: str
    scope: ScopeKind
    owner: str
    resource: str
    expected_visible: bool


@dataclass(frozen=True)
class QualifiedIdentityCase:
    """One qualified identity round-trip case."""

    description: str
    text: str
    expected_identity: ResourceIdentity | DeclarationIdentity


@dataclass(frozen=True)
class ExpectedBooleanCase:
    """One scalar boolean behavior case."""

    description: str
    expected_result: bool


@dataclass(frozen=True)
class ScopeReportTargetCase:
    """Expected target resolution result for one scope report query."""

    description: str
    target: str
    expected_identity: str | None
    expected_codes: tuple[str, ...]


@dataclass(frozen=True)
class ExpectedErrorCase:
    """One mutation error behavior case."""

    description: str
    expected_error: type[BaseException]


@dataclass(frozen=True)
class InvalidIdentityCase:
    """One rejected qualified identity case."""

    description: str
    value: str
    expected_error: type[BaseException]


@dataclass(frozen=True)
class ResourceExpectation:
    """One expected canonical resource projection."""

    description: str
    expected_kind: str
    expected_name: str
    expected_path: str
    expected_root: str


@dataclass(frozen=True)
class VisibilityExpectation:
    """One expected declaration visibility classification."""

    description: str
    expected_name: str
    expected_visible_reason: VisibilityReason | None = None
    expected_inaccessible_reason: InaccessibleReason | None = None


@dataclass(frozen=True)
class PlacementValidationCase:
    """One exact declaration placement validation case."""

    description: str
    declaration_scope: ScopeKind
    declaration_owner: str | None
    declaration_path: str
    ownership_root: str
    root_resource_kind: ResourceKind | None
    consumer_paths: tuple[str, ...]
    expected_codes: tuple[ScopeDiagnosticCode, ...]
    expected_direct_codes: tuple[ScopeDiagnosticCode, ...] = ()
