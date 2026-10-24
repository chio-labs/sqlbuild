"""Loaders for the synthetic fulfilment source tables, generated in python.loaders._fulfilment."""

from python.loaders._registry import load

from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.loaders import loader


@loader
def fulfilment__shipments(ctx: LoaderContext) -> object:
    return load(ctx, "fulfilment__shipments")


@loader
def fulfilment__shipment_packages(ctx: LoaderContext) -> object:
    return load(ctx, "fulfilment__shipment_packages")


@loader
def fulfilment__carrier_webhooks(ctx: LoaderContext) -> object:
    return load(ctx, "fulfilment__carrier_webhooks")


@loader
def fulfilment__returns(ctx: LoaderContext) -> object:
    return load(ctx, "fulfilment__returns")


@loader
def fulfilment__return_inspections(ctx: LoaderContext) -> object:
    return load(ctx, "fulfilment__return_inspections")


@loader
def fulfilment__carrier_rate_cards(ctx: LoaderContext) -> object:
    return load(ctx, "fulfilment__carrier_rate_cards")


@loader
def fulfilment__delivery_slots(ctx: LoaderContext) -> object:
    return load(ctx, "fulfilment__delivery_slots")


@loader
def fulfilment__pick_tasks(ctx: LoaderContext) -> object:
    return load(ctx, "fulfilment__pick_tasks")


@loader
def fulfilment__delivery_exceptions(ctx: LoaderContext) -> object:
    return load(ctx, "fulfilment__delivery_exceptions")
