"""Engine runs for the golden output tests."""

from __future__ import annotations

import json

from scripts.compiler_differential.models import CommandOutcome, EngineRun

PROJECT_PATH: str = "/work/failure__unknown-ref/project"


def engine_run(*, engine: str, message: str, compiled_sql: str) -> EngineRun:
    """A one-command run whose first diagnostic carries `message` and one compiled model."""

    report: dict[str, object] = {
        "compile_timings": {"total": 1.5},
        "diagnostics": [{"code": "P001", "message": message, "severity": "error"}],
    }
    return EngineRun(
        engine=engine,
        outcomes=(
            CommandOutcome(
                label="compile", exit_code=1, stdout=json.dumps(report), stderr="done in 12ms\n"
            ),
        ),
        compiled={"marts/customer_totals.sql": compiled_sql.encode("utf-8")},
        manifest=json.dumps(
            {
                "metadata": {"generated_at": "now"},
                "child_map": {},
                "nodes": {
                    "model.orders.customer_totals": {
                        "name": "customer_totals",
                        "compiled_code": compiled_sql,
                        "raw_code": "SELECT 1",
                        "checksum": {"checksum": "abc"},
                        "config": {"materialized": "table"},
                    }
                },
                "sources": {},
                "macros": {},
                "parent_map": {"model.orders.customer_totals": []},
            }
        ),
        dag=None,
    )
