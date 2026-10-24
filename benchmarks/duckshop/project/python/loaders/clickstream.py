"""Loaders for the synthetic clickstream source tables, generated in python.loaders._clickstream."""

from python.loaders._registry import load

from sqlbuild.executor.load.models import LoaderContext
from sqlbuild.loaders import loader


@loader
def clickstream__web_events(ctx: LoaderContext) -> object:
    return load(ctx, "clickstream__web_events")


@loader
def clickstream__app_events(ctx: LoaderContext) -> object:
    return load(ctx, "clickstream__app_events")


@loader
def clickstream__search_queries(ctx: LoaderContext) -> object:
    return load(ctx, "clickstream__search_queries")


@loader
def clickstream__email_events(ctx: LoaderContext) -> object:
    return load(ctx, "clickstream__email_events")


@loader
def clickstream__experiment_assignments(ctx: LoaderContext) -> object:
    return load(ctx, "clickstream__experiment_assignments")
