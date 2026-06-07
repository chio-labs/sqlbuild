"""Runtime provider entrypoints for other SQLBuild domains."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.provider.classes.container import ProviderContainer
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.provider.helpers.injection import call_with_provider_injection


def invoke_with_providers(
    *,
    function: Callable[..., object],
    context: object,
    providers: ProviderContainer | None = None,
    supplied_kwargs: dict[str, object] | None = None,
) -> object:
    """Call a Python node function with optional provider injection."""

    return call_with_provider_injection(
        function=function,
        context=context,
        providers=providers,
        supplied_kwargs=supplied_kwargs,
    )


def _empty_provider_container() -> ProviderContainer:
    """Return an empty provider container for contexts without runtime providers."""

    return ProviderSession({}).providers
