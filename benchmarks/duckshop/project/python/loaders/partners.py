"""Loaders for the synthetic partners source tables, generated in python.loaders._partners."""

from python.loaders._registry import load

from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.loaders import loader


@loader
def partners__partner_orders(ctx: LoaderContext) -> object:
    return load(ctx, "partners__partner_orders")


@loader
def partners__partner_listings(ctx: LoaderContext) -> object:
    return load(ctx, "partners__partner_listings")


@loader
def partners__partner_settlements(ctx: LoaderContext) -> object:
    return load(ctx, "partners__partner_settlements")
