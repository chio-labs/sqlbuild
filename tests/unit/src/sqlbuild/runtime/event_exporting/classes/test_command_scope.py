from __future__ import annotations

import time
from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredEventExporter, DiscoveredProvider
from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope
from sqlbuild.runtime.event_exporting.classes.dispatcher import EventExporterDispatcher
from sqlbuild.runtime.event_exporting.models import EventExportSummary
from tests.unit.src.sqlbuild.runtime.event_exporting.classes._test_types import (
    EventExporterTeardownTestCase,
)
from tests.unit.src.sqlbuild.runtime.event_exporting.classes.helpers import (
    BlockingProvider,
    blocking_discovery,
    lifecycle_event,
)


@pytest.mark.parametrize(
    "test_case",
    (EventExporterTeardownTestCase("deferred provider teardown", 1),),
    ids=lambda case: case.description,
)
def test_given_live_timed_out_exporter_when_scope_closes_then_provider_waits_for_invocation(
    test_case: EventExporterTeardownTestCase,
    tmp_path: Path,
) -> None:
    BlockingProvider.reset()
    providers: tuple[DiscoveredProvider, ...]
    exporters: tuple[DiscoveredEventExporter, ...]
    providers, exporters = blocking_discovery()
    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        shutdown_timeout_seconds=0.02,
        invocation_timeout_seconds=10.0,
    )
    scope: EventExporterCommandScope = EventExporterCommandScope(dispatcher=dispatcher)
    scope.configure_extensions(
        project_dir=tmp_path,
        providers=providers,
        event_exporters=exporters,
    )
    dispatcher.enqueue(lifecycle_event())
    assert BlockingProvider.entered.wait(timeout=0.2)
    started: float = time.monotonic()

    summary: EventExportSummary = scope.close()

    assert time.monotonic() - started < 0.2
    assert summary.failed == 1
    assert BlockingProvider.teardown_count == 0
    BlockingProvider.release_export.set()
    assert BlockingProvider.teardown_finished.wait(timeout=0.2)
    assert BlockingProvider.teardown_count == test_case.expected_teardown_count
    _ = scope.close()
    assert BlockingProvider.teardown_count == test_case.expected_teardown_count
