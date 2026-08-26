"""Dataclass-backed scope unit test cases."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.scopes.models import DeclarationIdentity, ResourceIdentity
from sqlbuild.compiler.scopes.types import ScopeKind


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
