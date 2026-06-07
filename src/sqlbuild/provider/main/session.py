"""Provider session entrypoint for other SQLBuild domains."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProvider
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.provider.helpers.session import build_provider_session as _build_provider_session


def build_provider_session(
    discovered_providers: tuple[DiscoveredProvider, ...],
    *,
    setup_context: object | None = None,
) -> ProviderSession:
    """Build a runtime provider session with fresh provider instances."""

    return _build_provider_session(
        discovered_providers=discovered_providers,
        setup_context=setup_context,
    )
