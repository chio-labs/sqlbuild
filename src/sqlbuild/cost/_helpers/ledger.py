"""Best-effort append-only statement telemetry persistence."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.cost.constants import COST_TELEMETRY_HEALTH
from sqlbuild.cost.exceptions import CostArtifactError
from sqlbuild.cost.models import CostResourceContext, StatementLedgerEntry

_LOCK: threading.Lock = threading.Lock()


def record_statement(
    *,
    context: CostResourceContext,
    statement_id: str,
    sql: str,
    query_id: object,
    status: str,
    started_at: datetime,
    completed_at: datetime,
    error: Exception | None = None,
) -> None:
    """Append statement identity without allowing telemetry I/O to affect execution."""

    if context.ledger_path is None:
        return
    try:
        _append_statement(
            path=context.ledger_path,
            payload={
                "run_id": context.run_id,
                "statement_id": statement_id,
                "resource_type": context.resource_type,
                "resource_name": context.resource_name,
                "phase": context.phase,
                "attempt": context.attempt,
                "query_id": query_id if isinstance(query_id, str) and query_id else None,
                "status": status,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "sql_sha256": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                "error_type": None if error is None else type(error).__name__,
            },
        )
    except Exception as error:
        COST_TELEMETRY_HEALTH.mark_ledger_failure(run_id=context.run_id, error=error)
        return


def read_statement_ledger(*, path: Path, run_id: str) -> tuple[StatementLedgerEntry, ...]:
    """Read a stable snapshot of valid statement ledger entries."""

    if not path.is_file():
        return ()
    entries: list[StatementLedgerEntry] = []
    with _LOCK:
        try:
            lines: list[str] = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            COST_TELEMETRY_HEALTH.mark_ledger_failure(run_id=run_id, error=error)
            return ()
    for line in lines:
        try:
            payload: dict[str, Any] = json.loads(line)
            query_id_value: object = payload.get("query_id")
            entries.append(
                StatementLedgerEntry(
                    statement_id=str(payload["statement_id"]),
                    run_id=str(payload["run_id"]),
                    resource_type=str(payload["resource_type"]),
                    resource_name=str(payload["resource_name"]),
                    phase=str(payload["phase"]),
                    attempt=int(payload["attempt"]),
                    query_id=(
                        query_id_value
                        if isinstance(query_id_value, str) and query_id_value
                        else None
                    ),
                    status=str(payload["status"]),
                    started_at=datetime.fromisoformat(str(payload["started_at"])),
                    completed_at=datetime.fromisoformat(str(payload["completed_at"])),
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            COST_TELEMETRY_HEALTH.mark_ledger_failure(
                run_id=run_id,
                error=CostArtifactError(f"invalid statement ledger entry ({type(error).__name__})"),
            )
            continue
    return tuple(entries)


def _append_statement(*, path: Path, payload: dict[str, object]) -> None:
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
            file.flush()
