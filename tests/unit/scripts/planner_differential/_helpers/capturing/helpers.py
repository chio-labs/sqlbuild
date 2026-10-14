"""Masks and plan-like values for the canonicalisation tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from scripts.planner_differential.models import TextMasks

RUN_DATE: date = date(2026, 10, 14)
TEST_MASKS: TextMasks = TextMasks(
    replacements=(
        ("/runs/work/orders/project", "<project>"),
        ("/runs/work", "<work>"),
    ),
    today=RUN_DATE,
)
LONG_QUERY: str = "SELECT order_id FROM orders WHERE status = 'shipped'\n" * 30


@dataclass(frozen=True)
class OrderPlanEntry:
    """A plan entry shaped like the planner's: a name, a query and an invocation time."""

    name: str
    query: str
    invocation_time: datetime
    data_start: datetime


@dataclass(frozen=True)
class OrderPlan:
    """A plan holding the same large entry twice, so the capture shares it."""

    entries: tuple[OrderPlanEntry, ...]


def order_plan() -> OrderPlan:
    """Return a plan whose entries repeat one large query and carry a volatile time."""

    entry: OrderPlanEntry = OrderPlanEntry(
        name="order_totals",
        query=LONG_QUERY,
        invocation_time=datetime(2026, 10, 14, 9, 30, tzinfo=UTC),
        data_start=datetime(2026, 4, 1, tzinfo=UTC),
    )
    return OrderPlan(entries=(entry, entry))


def expected_order_entry() -> dict[str, object]:
    """Return the canonical form of one `order_plan()` entry."""

    return {
        "__type__": f"{__name__}:OrderPlanEntry",
        "name": "order_totals",
        "query": LONG_QUERY,
        "invocation_time": "<volatile>",
        "data_start": {"__datetime__": "2026-04-01T00:00:00+00:00"},
    }
