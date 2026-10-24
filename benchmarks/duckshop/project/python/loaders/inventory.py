"""Loaders for the synthetic inventory source tables, generated in python.loaders._inventory."""

from python.loaders._registry import load

from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.loaders import loader


@loader
def inventory__warehouses(ctx: LoaderContext) -> object:
    return load(ctx, "inventory__warehouses")


@loader
def inventory__stock_movements(ctx: LoaderContext) -> object:
    return load(ctx, "inventory__stock_movements")


@loader
def inventory__stock_counts(ctx: LoaderContext) -> object:
    return load(ctx, "inventory__stock_counts")


@loader
def inventory__purchase_orders(ctx: LoaderContext) -> object:
    return load(ctx, "inventory__purchase_orders")


@loader
def inventory__po_receipts(ctx: LoaderContext) -> object:
    return load(ctx, "inventory__po_receipts")


@loader
def inventory__stock_transfers(ctx: LoaderContext) -> object:
    return load(ctx, "inventory__stock_transfers")


@loader
def inventory__stock_reservations(ctx: LoaderContext) -> object:
    return load(ctx, "inventory__stock_reservations")


@loader
def inventory__bin_locations(ctx: LoaderContext) -> object:
    return load(ctx, "inventory__bin_locations")
