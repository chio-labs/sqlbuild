"""Enums used by the compiler-owned scope domain."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import PurePath

    from sqlbuild.compiler.scopes.models import (
        DeclarationIdentity,
        DeclarationRecord,
        ResourceIdentity,
    )

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type NativeIdentityRow = tuple[str, str]
type NativeDeclarationIdentityRow = tuple[str, str, NativeIdentityRow | None]
type NativeResourceRow = tuple[str, str, str, str]
type NativeDeclarationRow = tuple[
    str,
    str,
    NativeIdentityRow | None,
    str,
    int,
    str,
    str | None,
    str,
    str | None,
    list[NativeDeclarationIdentityRow],
]
type NativeQualifiedRow = NativeDeclarationIdentityRow
type NativeUsageKeyRow = tuple[
    NativeQualifiedRow, NativeQualifiedRow, str, NativeQualifiedRow | None, str | None
]
type NativeRootRow = tuple[str, str, str | None]
type NativeResourceRecordRow = tuple[NativeIdentityRow, str, NativeRootRow]
type ScopeDeclarationPairs[Value] = tuple[tuple[DeclarationRecord, Value], ...]
type NativeResolvedRows = tuple[
    list[tuple[int, str, int | None]], list[tuple[int, str]], str | None
]
type ScopeQueryTarget = str | PurePath | ResourceIdentity | DeclarationIdentity
type NativeScopeTargetRow = tuple[NativeQualifiedRow | None, str, bool]
type NativeScopeFiltersRow = tuple[
    list[str], bool, str | None, list[str], str | None, bool, int, str, str | None, int, int, str
]
type NativeScopeValuesRow = tuple[
    tuple[list[str], list[NativeQualifiedRow], str] | None,
    tuple[list[str], str] | None,
    tuple[str, str | None, int | None, bool, str | None] | None,
]
type NativeScopeCompletenessRow = tuple[bool, bool, bool, bool, bool, bool]
type NativeScopeDiagnosticRow = tuple[
    str,
    str,
    str,
    str | None,
    int | None,
    int | None,
    NativeQualifiedRow | None,
    NativeIdentityRow | None,
]
type NativeScopeRaisedRow = tuple[int | None, tuple[str, str, str | None] | None]
type NativeScopeDeclarationRow = tuple[
    tuple[str, str, str, str | None, tuple[str, int, int], str, str | None],
    tuple[tuple[str, str | None] | None, str | None, list[tuple[str, object]]],
    tuple[list[str], list[str], list[str], str | None, str | None, list[str]],
]
type NativeScopeSectionRow = tuple[
    str, int, int, bool, int, bool, bool, str | None, str | None, int
]
type NativeScopeResourceReportRow = tuple[str, str | None, str | None, bool, bool, int]
type NativeScopeExplanationRow = tuple[NativeScopeDeclarationRow | None, bool]
type NativeScopeMoveRow = tuple[
    str,
    str,
    str | None,
    list[NativeScopeDeclarationRow],
    list[NativeScopeDeclarationRow],
    list[NativeScopeDeclarationRow],
    list[str],
    list[NativeScopeDeclarationRow],
    list[NativeScopeDeclarationRow],
    bool,
]
type NativeScopeFolderRow = tuple[str, str, int, int, int, list[tuple[str, int]]]
type NativeScopeReportRow[Diagnostic] = tuple[
    NativeScopeResourceReportRow,
    list[tuple[str, str, int]],
    list[NativeScopeDeclarationRow],
    list[NativeScopeDeclarationRow],
    list[NativeScopeDeclarationRow],
    list[NativeScopeDeclarationRow],
    NativeScopeFiltersRow,
    list[NativeScopeSectionRow],
    NativeScopeExplanationRow | None,
    NativeScopeMoveRow | None,
    list[Diagnostic],
    bool,
]
type NativeScopeBrowseRow[Diagnostic] = tuple[
    str, list[NativeScopeFolderRow], list[Diagnostic], bool
]
type NativeScopeListRow[Diagnostic] = tuple[
    str, list[NativeScopeDeclarationRow], NativeScopeSectionRow, list[Diagnostic]
]
type NativeScopeFailureRow = tuple[str, str] | None
type NativePlacementRows = tuple[
    list[tuple[NativeIdentityRow, str, NativeRootRow]],
    list[tuple[NativeQualifiedRow, str, int, int, str, NativeRootRow, str | None]],
    list[tuple[NativeQualifiedRow, NativeQualifiedRow, NativeQualifiedRow | None]],
]


class ResourceKind(StrEnum):
    """Kinds of authored resources represented in a scope index."""

    MODEL = "model"
    TEST = "test"
    SCENARIO = "scenario"
    FUNCTION = "function"
    SOURCE = "source"
    SEED = "seed"


class DeclarationKind(StrEnum):
    """Independent public declaration namespaces."""

    MACRO = "macro"
    ENUM = "enum"
    CONSTANT = "constant"
    AUDIT = "audit"
    SINGULAR_AUDIT = "singular_audit"
    SCHEMA = "schema"
    SQL_HOOK = "sql_hook"
    PYTHON_HOOK = "python_hook"


class ScopeKind(StrEnum):
    """Compiler-enforced declaration visibility tiers."""

    GLOBAL = "global"
    INHERITED = "inherited"
    LOCAL = "local"
    PRIVATE = "private"


class OwnershipRootKind(StrEnum):
    """How an ownership root participates in authored resource scope."""

    RESOURCE = "resource"
    GLOBAL = "global"


class UsageKind(StrEnum):
    """Why one indexed identity consumes a declaration."""

    RUNTIME = "runtime"
    GENERATED = "generated"
    DECLARATION_DEPENDENCY = "declaration_dependency"


class GrantKind(StrEnum):
    """Compiler relationships that grant additional public vocabulary."""

    EXPECTED_MODEL = "expected_model"
    TESTED_MACRO = "tested_macro"


class VisibilityReason(StrEnum):
    """Positive explanations emitted by the canonical resolver."""

    GLOBAL = "global"
    INHERITED_ANCESTOR = "inherited_ancestor"
    LOCAL_OWNER = "local_owner"
    PRIVATE_OWNER = "private_owner"
    EXPECTED_MODEL = "expected_model"
    TESTED_MACRO = "tested_macro"


class InaccessibleReason(StrEnum):
    """Stable explanations for declarations outside effective scope."""

    LOCAL_BOUNDARY = "local_boundary"
    SIBLING_SCOPE = "sibling_scope"
    DESCENDANT_SCOPE = "descendant_scope"
    UNRELATED_SCOPE = "unrelated_scope"
    PRIVATE_OWNER = "private_owner"
    UNSUPPORTED_RESOURCE_KIND = "unsupported_resource_kind"


class DiagnosticSeverity(StrEnum):
    """Severity of a stable scope diagnostic."""

    ERROR = "error"
    WARNING = "warning"


class ScopeDiagnosticCode(StrEnum):
    """Stable diagnostic identities shared by future scope consumers."""

    UNKNOWN_TARGET = "S001"
    UNQUALIFIED_TARGET = "S002"
    DUPLICATE_DECLARATION = "S003"
    INVALID_DECLARATION_NAME = "S004"
    RESERVED_DECLARATION_NAME = "S005"
    INACCESSIBLE_DECLARATION = "S006"
    LOCAL_NEEDED_BY_DESCENDANT = "S007"
    OVER_BROAD_INHERITED = "S008"
    REQUIRES_GLOBAL_PLACEMENT = "S009"
    UNUSED_DECLARATION = "S010"
    INVALID_PROSPECTIVE_PATH = "S011"
    NESTED_DECLARATION_ROOT = "S012"
    INCOMPLETE_USAGE = "S013"
    INVALID_CURSOR = "S014"
    MACRO_MODULE_IMPORT = "S015"
    INVALID_MACRO_DEPENDENCY = "S016"
    MACRO_DEPENDENCY_CYCLE = "S017"
    DUPLICATE_RESOURCE = "S018"
    RESOURCE_PARSE_ERROR = "S019"
    DECLARATION_PARSE_ERROR = "S020"
    MACRO_PARSE_ERROR = "S021"
    RELATIONSHIP_PARSE_ERROR = "S022"
    CONFIG_PARSE_ERROR = "S023"
    OVER_BROAD_GLOBAL = "S024"


class CompletenessSection(StrEnum):
    """Independently tracked scope-index analysis sections."""

    DISCOVERY = "discovery"
    STATIC_VISIBILITY = "static_visibility"
    RUNTIME_USAGE = "runtime_usage"
    RELATIONSHIPS = "relationships"
    PLACEMENT = "placement"
    PROMOTION_IMPACT = "promotion_impact"
