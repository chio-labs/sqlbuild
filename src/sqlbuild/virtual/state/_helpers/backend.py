"""State backend construction helpers."""

from __future__ import annotations

from sqlbuild.virtual.state.classes.duckdb import DuckDbStateBackend
from sqlbuild.virtual.state.classes.postgres import PostgresStateBackend
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.types import StateBackendName


def build_state_backend(backend_name: StateBackendName) -> StateBackend:
    """Build the configured virtual state backend implementation."""

    match backend_name:
        case StateBackendName.DUCKDB:
            return DuckDbStateBackend()
        case StateBackendName.POSTGRES:
            return PostgresStateBackend()
    raise StateBackendConfigError(f"Unsupported state backend: {backend_name}")
