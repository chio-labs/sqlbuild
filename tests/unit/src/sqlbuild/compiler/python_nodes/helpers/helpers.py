"""Helpers for internal Python-node helper tests."""

from __future__ import annotations

from sqlbuild.tasks import task


def fetch_events(_ctx: object) -> list[dict[str, object]]:
    return []


def load_events(_ctx: object) -> list[dict[str, object]]:
    return []


def prepare_orders(_ctx: object) -> None:
    return None


@task(name="prepare_orders")
def imported_prepare_orders(_ctx: object) -> None:
    return None


def export_orders(_ctx: object) -> None:
    return None


def check_orders_export(_ctx: object) -> bool:
    return True
