"""Enums used by the compiler-owned scope domain."""

from __future__ import annotations

from enum import StrEnum

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, object]


class ScopeCacheIdentityType(StrEnum):
    """Identity discriminator values persisted by the scope cache codec."""

    RESOURCE = "resource"
    DECLARATION = "declaration"


class ResourceKind(StrEnum):
    """Kinds of authored resources represented in a scope index."""

    MODEL = "model"
    TEST = "test"
    SCENARIO = "scenario"
    HOOK = "hook"
    FUNCTION = "function"
    AUDIT = "audit"
    SOURCE = "source"


class DeclarationKind(StrEnum):
    """Independent public declaration namespaces."""

    MACRO = "macro"
    ENUM = "enum"
    CONSTANT = "constant"


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


class VisibilityReason(StrEnum):
    """Positive explanations emitted by the canonical resolver."""

    GLOBAL = "global"
    INHERITED_ANCESTOR = "inherited_ancestor"
    LOCAL_OWNER = "local_owner"
    PRIVATE_OWNER = "private_owner"
    EXPECTED_MODEL = "expected_model"


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
