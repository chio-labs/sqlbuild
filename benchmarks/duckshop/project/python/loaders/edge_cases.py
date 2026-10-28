"""Loaders for the edge-case area's raw tables, with the fixed rows in python.loaders._edge_cases.

These rows are hand-picked edge values, not generated volume: `data_scale` does not change them,
and they never touch the core tables, so core outputs and expectations stay the same.
"""

from python.loaders._edge_cases import TABLES
from python.loaders._writer import statements

from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.loaders import loader


def _load(ctx: LoaderContext, source_name: str) -> object:
    rows = TABLES[source_name]
    for sql in statements(ctx.destination, source_name, rows):
        ctx.execute_sql(sql)
    return ctx.result(metadata={"rows": len(rows)})


@loader
def edge__partner_payloads(ctx: LoaderContext) -> object:
    return _load(ctx, "edge__partner_payloads")


@loader
def edge__gateway_callbacks(ctx: LoaderContext) -> object:
    return _load(ctx, "edge__gateway_callbacks")


@loader
def edge__price_windows(ctx: LoaderContext) -> object:
    return _load(ctx, "edge__price_windows")


@loader
def edge__customer_profiles(ctx: LoaderContext) -> object:
    return _load(ctx, "edge__customer_profiles")


@loader
def edge__ledger_entries(ctx: LoaderContext) -> object:
    return _load(ctx, "edge__ledger_entries")


@loader
def edge__ticket_notes(ctx: LoaderContext) -> object:
    return _load(ctx, "edge__ticket_notes")
