from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredProvider
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.provider.helpers.session import build_provider_session
from sqlbuild.providers import Provider
from tests.unit.src.sqlbuild.provider.helpers._test_types import BuildProviderSessionTestCase


class RuntimeFreshProvider(Provider):
    provider_name: ClassVar[str] = "runtime_fresh"
    events: ClassVar[list[str]] = []
    instance_ids: ClassVar[list[int]] = []

    def setup(self, ctx: object) -> None:
        self.events.append(f"setup:{ctx}")
        self.instance_ids.append(id(self))

    def teardown(self) -> None:
        self.events.append(f"teardown:{id(self)}")


@pytest.mark.parametrize(
    "test_case",
    [
        BuildProviderSessionTestCase(
            description="builds independent sessions with fresh provider instances",
            provider_name="runtime_fresh",
            expected_first_events=("setup:first",),
            expected_second_events=("setup:first", "setup:second"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_discovered_providers_when_building_sessions_then_each_session_gets_fresh_instances(
    test_case: BuildProviderSessionTestCase,
) -> None:
    RuntimeFreshProvider.events = []
    RuntimeFreshProvider.instance_ids = []
    settings: RuntimeFreshProvider = RuntimeFreshProvider()
    discovered_provider: DiscoveredProvider = DiscoveredProvider(
        file_path=Path(__file__),
        relative_path=Path(Path(__file__).name),
        name=test_case.provider_name,
        provider_class=RuntimeFreshProvider,
        settings=settings,
    )

    first_session: ProviderSession = build_provider_session(
        (discovered_provider,), setup_context="first"
    )
    second_session: ProviderSession = build_provider_session(
        (discovered_provider,), setup_context="second"
    )

    first_provider: Provider = first_session.providers[test_case.provider_name]
    assert tuple(RuntimeFreshProvider.events) == test_case.expected_first_events
    second_provider: Provider = second_session.providers[test_case.provider_name]

    assert first_provider is not second_provider
    assert first_provider is not settings
    assert second_provider is not settings
    assert len(set(RuntimeFreshProvider.instance_ids)) == 2
    assert tuple(RuntimeFreshProvider.events) == test_case.expected_second_events


@pytest.mark.parametrize(
    "test_case",
    [
        BuildProviderSessionTestCase(
            description="closing one built session does not teardown another session",
            provider_name="runtime_fresh",
            expected_first_events=("setup:first", "setup:second", "teardown:"),
            expected_second_events=("setup:first", "setup:second", "teardown:", "teardown:"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_two_built_sessions_when_closing_one_then_other_session_remains_active(
    test_case: BuildProviderSessionTestCase,
) -> None:
    RuntimeFreshProvider.events = []
    RuntimeFreshProvider.instance_ids = []
    discovered_provider: DiscoveredProvider = DiscoveredProvider(
        file_path=Path(__file__),
        relative_path=Path(Path(__file__).name),
        name=test_case.provider_name,
        provider_class=RuntimeFreshProvider,
        settings=RuntimeFreshProvider(),
    )
    first_session: ProviderSession = build_provider_session(
        (discovered_provider,), setup_context="first"
    )
    second_session: ProviderSession = build_provider_session(
        (discovered_provider,), setup_context="second"
    )
    first_session.providers[test_case.provider_name]
    second_session.providers[test_case.provider_name]

    first_session.close()

    first_event_prefixes: tuple[str, ...] = tuple(
        event if not event.startswith("teardown:") else "teardown:"
        for event in RuntimeFreshProvider.events
    )
    assert first_event_prefixes == test_case.expected_first_events
    second_session.providers[test_case.provider_name]
    second_session.close()
    second_event_prefixes: tuple[str, ...] = tuple(
        event if not event.startswith("teardown:") else "teardown:"
        for event in RuntimeFreshProvider.events
    )
    assert second_event_prefixes == test_case.expected_second_events
