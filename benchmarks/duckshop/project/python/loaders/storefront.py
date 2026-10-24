"""Loaders for the synthetic storefront source tables, generated in python.loaders._storefront."""

from python.loaders._registry import load

from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.loaders import loader


@loader
def storefront__customers(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__customers")


@loader
def storefront__customer_addresses(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__customer_addresses")


@loader
def storefront__customer_consents(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__customer_consents")


@loader
def storefront__loyalty_accounts(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__loyalty_accounts")


@loader
def storefront__loyalty_ledger(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__loyalty_ledger")


@loader
def storefront__wishlists(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__wishlists")


@loader
def storefront__gift_cards(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__gift_cards")


@loader
def storefront__gift_card_transactions(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__gift_card_transactions")


@loader
def storefront__orders(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__orders")


@loader
def storefront__order_lines(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__order_lines")


@loader
def storefront__order_status_events(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__order_status_events")


@loader
def storefront__payments(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__payments")


@loader
def storefront__refunds(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__refunds")


@loader
def storefront__promotions(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__promotions")


@loader
def storefront__promotion_redemptions(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__promotion_redemptions")


@loader
def storefront__carts(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__carts")


@loader
def storefront__reviews(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__reviews")


@loader
def storefront__subscriptions(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__subscriptions")


@loader
def storefront__subscription_events(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__subscription_events")


@loader
def storefront__store_credit_ledger(ctx: LoaderContext) -> object:
    return load(ctx, "storefront__store_credit_ledger")
