"""Provider-aware Python callable invocation helpers."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import get_type_hints

from sqlbuild.provider.classes.container import ProviderContainer
from sqlbuild.provider.exceptions import ProviderInjectionError, ProviderLookupError
from sqlbuild.providers import Provider

_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset({"ctx", "context", "_ctx"})


def call_with_provider_injection(
    *,
    function: Callable[..., object],
    context: object,
    providers: ProviderContainer | None = None,
) -> object:
    """Call a Python node function with context and name-based provider injection."""

    signature: inspect.Signature = inspect.signature(function)
    try:
        type_hints: dict[str, object] = get_type_hints(function)
    except TypeError:
        type_hints = {}
    kwargs: dict[str, object] = {}
    context_bound: bool = False
    for parameter in signature.parameters.values():
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        annotation: object = type_hints.get(parameter.name, parameter.annotation)
        if parameter.name in _CONTEXT_PARAMETER_NAMES:
            if providers is not None and parameter.name in providers:
                raise ProviderInjectionError(
                    f"Provider name '{parameter.name}' conflicts with reserved context parameter "
                    f"'{parameter.name}'"
                )
            kwargs[parameter.name] = context
            context_bound = True
            continue
        provider: Provider | None = _provider_for_parameter(
            parameter=parameter,
            annotation=annotation,
            providers=providers,
        )
        if provider is not None:
            kwargs[parameter.name] = provider
            continue
        if not context_bound and parameter.default is inspect.Parameter.empty:
            kwargs[parameter.name] = context
            context_bound = True
    return function(**kwargs)


def _provider_for_parameter(
    *,
    parameter: inspect.Parameter,
    annotation: object,
    providers: ProviderContainer | None,
) -> Provider | None:
    provider_annotation: type[Provider] | None = (
        annotation if isinstance(annotation, type) and issubclass(annotation, Provider) else None
    )
    expects_provider: bool = provider_annotation is not None
    if providers is None:
        if expects_provider:
            raise ProviderInjectionError(
                f"Provider parameter '{parameter.name}' requires provider '{parameter.name}', "
                "but no provider container is available"
            )
        return None
    if parameter.name not in providers:
        if expects_provider:
            raise ProviderInjectionError(
                f"Provider parameter '{parameter.name}' requires provider '{parameter.name}', "
                "but it was not found"
            )
        return None
    try:
        provider: Provider = providers[parameter.name]
    except ProviderLookupError as error:
        raise ProviderInjectionError(str(error)) from error
    if provider_annotation is not None and not isinstance(provider, provider_annotation):
        raise ProviderInjectionError(
            f"Provider parameter '{parameter.name}' expected {provider_annotation.__name__}, "
            f"but provider '{parameter.name}' is {provider.__class__.__name__}"
        )
    return provider
