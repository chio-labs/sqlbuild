"""Helpers for building runtime provider sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlbuild.compiler.discovery.models import DiscoveredProvider
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.providers import Provider

if TYPE_CHECKING:
    from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope


def build_provider_session(
    *,
    discovered_providers: tuple[DiscoveredProvider, ...],
    setup_context: object | None = None,
    allow_shared: bool = True,
) -> ProviderSession:
    """Build a runtime provider session with fresh provider instances."""

    if allow_shared:
        from sqlbuild.runtime.event_exporting.main.current_event_exporter_command_scope import (
            current_event_exporter_command_scope,
        )

        scope: EventExporterCommandScope | None = current_event_exporter_command_scope()
        if scope is not None and scope.provider_session is not None:
            expected_names: tuple[str, ...] = tuple(
                provider.name for provider in discovered_providers
            )
            if scope.provider_session.keys() == expected_names:
                return scope.provider_session
    providers: dict[str, Provider] = {
        discovered_provider.name: discovered_provider.provider_class()
        for discovered_provider in discovered_providers
    }
    return ProviderSession(providers, setup_context=setup_context)
