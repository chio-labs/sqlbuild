"""Output capture delivery defaults."""

from importlib.metadata import version

from sqlbuild._native import INVOCATION_CONTEXT_ENV as INVOCATION_CONTEXT_ENV

COMMAND_OUTPUT_SINK_RECORD_PARAMETER_NAME: str = "record"
SQLBUILD_COMMAND_OUTPUT_PRODUCER_VERSION: str = version("sqlbuild")
