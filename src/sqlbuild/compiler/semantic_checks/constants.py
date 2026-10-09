"""Native semantic completion statuses and deferral record sites."""

from sqlbuild.compiler.references.types import SqlReferenceKind

NATIVE_TYPE_RECOVERY_UNCHANGED: str = "unchanged"
NATIVE_TYPE_RECOVERY_DEFERRED: str = "deferred"
NATIVE_SEMANTIC_NO_CATALOG: str = "no_analysis_catalog"
NATIVE_SEMANTIC_FAILURE: str = "native_failure"
TYPE_RECOVERY_DEFERRAL_SITE: str = "type_recovery.py"
COMPLETION_DEFERRAL_SITE: str = "recovery.py"
METADATA_DEFERRAL_SITE: str = "metadata_validation.py"
UNKNOWN_RECOVERED_TYPE: str = "UNKNOWN"
METADATA_CONFIG_KEYS: tuple[str, ...] = (
    "unique_key",
    "cursor",
    "partition_column",
    "row_diff_exclude_columns",
)
METADATA_FUNCTION_REFERENCE_KINDS: frozenset[SqlReferenceKind] = frozenset(
    {SqlReferenceKind.UDF, SqlReferenceKind.TABLE_FUNCTION}
)
