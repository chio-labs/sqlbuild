"""Loaders for the synthetic finance source tables, generated in python.loaders._finance."""

from python.loaders._registry import load

from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.loaders import loader


@loader
def finance__invoices(ctx: LoaderContext) -> object:
    return load(ctx, "finance__invoices")


@loader
def finance__ledger_entries(ctx: LoaderContext) -> object:
    return load(ctx, "finance__ledger_entries")


@loader
def finance__payouts(ctx: LoaderContext) -> object:
    return load(ctx, "finance__payouts")


@loader
def finance__tax_rates(ctx: LoaderContext) -> object:
    return load(ctx, "finance__tax_rates")


@loader
def finance__chargebacks(ctx: LoaderContext) -> object:
    return load(ctx, "finance__chargebacks")


@loader
def finance__settlement_reports(ctx: LoaderContext) -> object:
    return load(ctx, "finance__settlement_reports")
