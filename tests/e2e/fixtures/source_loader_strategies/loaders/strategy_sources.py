from datetime import datetime
from typing import Any

from sqlbuild.loaders import loader


@loader
def raw_countries(ctx: object) -> list[dict[str, object]]:
    _ = ctx
    return [
        {"country_id": 1, "country_code": "US", "country_name": "United States"},
        {"country_id": 2, "country_code": "CA", "country_name": "Canada"},
    ]


@loader
def raw_webhook_events(ctx: object) -> list[dict[str, object]]:
    _ = ctx
    return [
        {"event_id": 101, "event_name": "signup"},
        {"event_id": 102, "event_name": "checkout"},
    ]


@loader
def raw_order_events(ctx: Any) -> list[dict[str, object]]:
    if ctx.current_cursor_value is None:
        return [
            {
                "event_id": 201,
                "event_at": datetime(2026, 5, 1, 0, 0, 0),
                "amount_cents": 1000,
            },
            {
                "event_id": 202,
                "event_at": datetime(2026, 5, 1, 1, 0, 0),
                "amount_cents": 2000,
            },
        ]
    return [
        {
            "event_id": 202,
            "event_at": datetime(2026, 5, 1, 1, 0, 0),
            "amount_cents": 2500,
        },
        {
            "event_id": 203,
            "event_at": datetime(2026, 5, 1, 2, 0, 0),
            "amount_cents": 3000,
        },
    ]


@loader
def raw_customers(ctx: Any) -> list[dict[str, object]]:
    if ctx.current_cursor_value is None:
        return [
            {
                "customer_id": 1,
                "plan_name": "basic",
                "updated_at": datetime(2026, 5, 1, 0, 0, 0),
            },
            {
                "customer_id": 2,
                "plan_name": "trial",
                "updated_at": datetime(2026, 5, 1, 0, 0, 0),
            },
        ]
    return [
        {
            "customer_id": 1,
            "plan_name": "pro",
            "updated_at": datetime(2026, 5, 2, 0, 0, 0),
        },
        {
            "customer_id": 3,
            "plan_name": "enterprise",
            "updated_at": datetime(2026, 5, 2, 0, 0, 0),
        },
    ]


@loader
def raw_loader_status(ctx: Any) -> None:
    ctx.execute_sql(f"DROP TABLE IF EXISTS {ctx.target}")
    ctx.execute_sql(
        f"CREATE TABLE {ctx.target} AS "
        "SELECT 1 AS status_id, 'loaded' AS status_name, 'self_managed' AS loaded_by"
    )
