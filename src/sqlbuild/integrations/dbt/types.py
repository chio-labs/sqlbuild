"""dbt integration type aliases."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

type DbtInvoker = Callable[[tuple[str, ...], Path | None], object]


class DbtCombinedGraphOwner(StrEnum):
    """Owner namespace for a combined dbt/SQLBuild graph node."""

    DBT = "dbt"
    SQLBUILD = "sqb"


class DbtCombinedGraphResourceType(StrEnum):
    """Resource type namespace for a combined dbt/SQLBuild graph node."""

    MODEL = "model"
    SOURCE = "source"


class DbtInteropCommand(StrEnum):
    """dbt interop commands with SQLBuild participation."""

    PLAN = "plan"
    RUN = "run"
    BUILD = "build"
    TEST = "test"
    DEBUG = "debug"
    LINEAGE = "lineage"


class DbtLineageDirection(StrEnum):
    """Traversal direction for mixed dbt/SQLBuild lineage."""

    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    BOTH = "both"


class DbtLineageOutputFormat(StrEnum):
    """Output format for mixed dbt/SQLBuild lineage."""

    TREE = "tree"
    JSON = "json"
    LIST = "list"


class DbtInteropSqlbuildTestAction(StrEnum):
    """SQLBuild validation actions used by `sqb dbt test`."""

    TEST = "test"
    AUDIT = "audit"


class DbtInteropSkipReason(StrEnum):
    """Reason one side of a dbt interop plan has no work."""

    NO_DBT_WORK = "no_dbt_work"
    DBT_MODELS_CURRENT = "dbt_models_current"
    NO_SQLBUILD_WORK = "no_sqlbuild_work"


class DbtModelPlanAction(StrEnum):
    """Planner action for one dbt model node."""

    RUN = "run"
    CURRENT = "current"
    BLOCKED = "blocked"


class DbtModelPlanReason(StrEnum):
    """Planner reason for one dbt model node action."""

    FIRST_RUN = "first_run"
    FULL_REFRESH = "full_refresh"
    RELATION_MISSING = "relation_missing"
    CHECKSUM_CHANGED = "checksum_changed"
    UPSTREAM_CHANGED = "upstream_changed"
    SOURCE_FRESHNESS_CHANGED = "source_freshness_changed"
    NO_CHANGE = "no_change"
    SOURCE_FRESHNESS_ERROR = "source_freshness_error"


class DbtModelOutcomeState(StrEnum):
    """SQLBuild-facing state for one dbt model outcome."""

    CHANGED = "changed"
    CURRENT = "current"
    BLOCKING = "blocking"


class DbtReuseCandidateSkipReason(StrEnum):
    """Reason a scoped dbt node is not a physical reuse candidate."""

    CURRENT_MANIFEST_MISSING = "current_manifest_missing"
    REUSE_MANIFEST_MISSING = "reuse_manifest_missing"
    VIEW = "view"
    EPHEMERAL = "ephemeral"
    UNSUPPORTED_MATERIALIZATION = "unsupported_materialization"


class DbtReusePlanAction(StrEnum):
    """Planned dbt reuse_from action for one scoped dbt node."""

    CURRENT = "current"
    COMPLETE_REUSE = "complete_reuse"
    SEEDED_REUSE = "seeded_reuse"
    REBUILD = "rebuild"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class DbtReusePlanReason(StrEnum):
    """Reason for one dbt reuse_from plan action."""

    DESTINATION_CURRENT = "destination_current"
    DESTINATION_MISSING = "destination_missing"
    FINGERPRINT_MISSING = "fingerprint_missing"
    FINGERPRINT_CHANGED = "fingerprint_changed"
    FULL_REFRESH = "full_refresh"
    SOURCE_FRESHNESS_BLOCK = "source_freshness_block"
    NON_PHYSICAL_RESOURCE = "non_physical_resource"
    MANIFEST_NODE_MISSING = "manifest_node_missing"
    REUSE_METADATA_INVALID = "reuse_metadata_invalid"
    ORIGIN_RELATION_MISSING = "origin_relation_missing"


class DbtReuseExecutionMode(StrEnum):
    """dbt fingerprint execution mode values written by reuse_from."""

    REUSE = "reuse"


class DbtReuseMode(StrEnum):
    """dbt reuse_from physical reuse modes."""

    COMPLETE = "complete"
    SEEDED = "seeded"


class DbtReuseMetadataStatus(StrEnum):
    """dbt reuse_from fingerprint metadata status values."""

    SUCCESS = "success"
