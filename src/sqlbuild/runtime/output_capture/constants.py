"""Output capture delivery defaults."""

from importlib.metadata import version

DEFAULT_OUTPUT_BATCH_SIZE: int = 64
DEFAULT_OUTPUT_MAX_RECORD_BYTES: int = 64 * 1024
DEFAULT_OUTPUT_FLUSH_INTERVAL_SECONDS: float = 0.25
DEFAULT_OUTPUT_QUEUE_CAPACITY: int = 1024
DEFAULT_OUTPUT_SHUTDOWN_TIMEOUT_SECONDS: float = 2.0
MIN_OUTPUT_RECORD_BYTES: int = 4
INVOCATION_CONTEXT_ENV: str = "SQLBUILD_INVOCATION_CONTEXT_JSON"
MAX_INVOCATION_CONTEXT_BYTES: int = 16 * 1024
MAX_INVOCATION_CONTEXT_DEPTH: int = 8
CURRENT_COMMAND_OUTPUT_SCHEMA_VERSION: int = 1
COMMAND_OUTPUT_RECORD_TYPE: str = "command_output"
COMMAND_OUTPUT_LOSS_RECORD_TYPE: str = "command_output_loss"
COMMAND_OUTPUT_SINK_RECORD_PARAMETER_NAME: str = "record"
COMMAND_OUTPUT_ENVELOPE_FIELDS: frozenset[str] = frozenset(
    {
        "record_id",
        "record_type",
        "schema_version",
        "producer",
        "producer_version",
        "occurred_at",
        "invocation_id",
        "run_id",
        "sequence",
        "stream",
        "message",
        "chunk_index",
        "chunk_count",
        "priority",
        "dropped_records",
        "external_context",
    }
)
SQLBUILD_COMMAND_OUTPUT_PRODUCER_VERSION: str = version("sqlbuild")
