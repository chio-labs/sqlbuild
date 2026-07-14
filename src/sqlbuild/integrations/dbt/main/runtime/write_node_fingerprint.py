"""Write a dbt node fingerprint."""

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.integrations.dbt._helpers.manifest.fingerprinting import (
    try_write_dbt_node_fingerprint as _write,
)
from sqlbuild.integrations.dbt.models import DbtFingerprintDestination, DbtNodeExecutionResult


def try_write_dbt_node_fingerprint(
    *,
    result: DbtNodeExecutionResult,
    adapter: BaseAdapter,
    connection: Any,
    destination: DbtFingerprintDestination,
    warnings: list[str],
    query_sql: str | None = None,
    seed_identity_hash: str | None = None,
    version_hash_override: str | None = None,
) -> list[str]:
    """Best-effort append one successful dbt node fingerprint."""

    return _write(
        result=result,
        adapter=adapter,
        connection=connection,
        destination=destination,
        warnings=warnings,
        query_sql=query_sql,
        seed_identity_hash=seed_identity_hash,
        version_hash_override=version_hash_override,
    )
