"""Provider session entrypoint for other SQLBuild domains."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProvider
from sqlbuild.provider._helpers.session import build_provider_session as _build_provider_session
from sqlbuild.provider.classes.session import ProviderSession


def build_provider_session(
    *,
    discovered_providers: tuple[DiscoveredProvider, ...],
    setup_context: object | None = None,
    allow_shared: bool = True,
) -> ProviderSession:
    """Build a runtime provider session with fresh provider instances."""

    return _build_provider_session(
        discovered_providers=discovered_providers,
        setup_context=setup_context,
        allow_shared=allow_shared,
    )
