"""Native semantic completion statuses and inputs."""

from sqlbuild.compiler.references.types import SqlReferenceKind

NATIVE_TYPE_RECOVERY_UNCHANGED: str = "unchanged"
NATIVE_SEMANTIC_NO_CATALOG: str = (
    "NativeCompilerError: native semantic completion: the project has no analysis catalog"
)
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
