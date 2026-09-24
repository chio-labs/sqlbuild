"""Local helpers for audit command E2E tests."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

ORDER_COLUMNS: tuple[str, ...] = tuple(f"order_attribute_{index:02d}" for index in range(12))


def delivery_project_toml(*, lifecycle_config: str) -> str:
    """Return a DuckDB project config with optional lifecycle sink settings."""

    return (
        dedent(
            """
            name = "audit_event_delivery"
            adapter = "duckdb"

            [connection]
            database = "audit_event_delivery.duckdb"
            """
        ).lstrip()
        + lifecycle_config
    )


def delivery_model_files() -> dict[str, str]:
    """Return a customers -> orders chain carrying one plus twelve column audits."""

    columns: str = "\n".join(f"    {name} (audits [not_null])," for name in ORDER_COLUMNS)
    selected: str = ",\n  ".join(f"1 AS {name}" for name in ORDER_COLUMNS)
    return {
        "models/customers.sql": dedent(
            """
            MODEL (
              materialized table,
              columns (
                customer_id (audits [not_null]),
              ),
            );

            SELECT 1 AS customer_id
            """
        ).lstrip(),
        "models/orders.sql": (
            "MODEL (\n  materialized table,\n  columns (\n"
            f"{columns}\n"
            "  ),\n);\n\n"
            f"SELECT\n  customer_id,\n  {selected}\n"
            'FROM __ref("customers")\n'
        ),
    }


def recording_sink_source(*, event_kinds: str, delay_seconds: float) -> str:
    """Return a lifecycle sink that appends each event to ORDERS_EVENT_PATH after a delay."""

    return dedent(
        f"""
        import os
        import time
        from pathlib import Path

        from sqlbuild.sinks import (
            LifecycleEvent,
            LifecycleEventKind,
            lifecycle_event_sink,
            lifecycle_event_to_json,
        )


        @lifecycle_event_sink(name="slow_orders_events", event_kinds={event_kinds})
        def record_event(event: LifecycleEvent) -> None:
            time.sleep({delay_seconds})
            path = Path(os.environ["ORDERS_EVENT_PATH"])
            with path.open("a", encoding="utf-8") as stream:
                stream.write(lifecycle_event_to_json(event) + "\\n")
        """
    ).lstrip()


def read_sequenced_events(path: Path) -> list[dict[str, object]]:
    """Return recorded events ordered by canonical invocation sequence."""

    events: list[dict[str, object]] = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    return sorted(events, key=lambda event: int(str(event["invocation_sequence"])))


def events_of_type(events: list[dict[str, object]], event_type: str) -> list[dict[str, object]]:
    """Return events with one lifecycle type in their existing order."""

    return list(filter(lambda event: event["event_type"] == event_type, events))
