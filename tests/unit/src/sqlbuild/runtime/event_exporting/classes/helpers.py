from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import ClassVar

from sqlbuild.compiler.discovery.models import (
    DiscoveredEventExporter,
    DiscoveredProvider,
    DiscoveredProviderUsage,
)
from sqlbuild.observability import LifecycleEvent
from sqlbuild.providers import Provider
from sqlbuild.runtime.event_exporting.models import (
    LifecycleExportPolicy,
    QueuedLifecycleEvent,
)


class BlockingProvider(Provider):
    entered: ClassVar[Event] = Event()
    release_export: ClassVar[Event] = Event()
    teardown_finished: ClassVar[Event] = Event()
    teardown_count: ClassVar[int] = 0

    @classmethod
    def reset(cls) -> None:
        cls.entered.clear()
        cls.release_export.clear()
        cls.teardown_finished.clear()
        cls.teardown_count = 0

    def export(self) -> None:
        self.entered.set()
        self.release_export.wait()

    def teardown(self) -> None:
        type(self).teardown_count += 1
        self.teardown_finished.set()


def blocking_exporter(*, event: LifecycleEvent, blocking_provider: BlockingProvider) -> None:
    del event
    blocking_provider.export()


def blocking_discovery() -> tuple[
    tuple[DiscoveredProvider, ...], tuple[DiscoveredEventExporter, ...]
]:
    provider_path: Path = Path("providers/blocking.py")
    exporter_path: Path = Path("event_exporters/blocking.py")
    provider: DiscoveredProvider = DiscoveredProvider(
        file_path=provider_path,
        relative_path=provider_path,
        name="blocking_provider",
        provider_class=BlockingProvider,
        settings=BlockingProvider(),
    )
    exporter: DiscoveredEventExporter = DiscoveredEventExporter(
        file_path=exporter_path,
        relative_path=exporter_path,
        name="blocking_exporter",
        function=blocking_exporter,
        provider_usages=(
            DiscoveredProviderUsage(
                provider_name="blocking_provider",
                parameter_name="blocking_provider",
                annotation_class_name="BlockingProvider",
                annotation_module=__name__,
            ),
        ),
    )
    return (provider,), (exporter,)


def lifecycle_event(index: int = 1, event_type: str = "invocation_started") -> LifecycleEvent:
    return LifecycleEvent(
        event_id=f"event-{index}",
        event_type=event_type,
        schema_version=1,
        producer="test",
        producer_version="1",
        occurred_at=datetime.now(UTC),
        invocation_id="invocation",
        payload={"command": "build"},
    )


def queued_event(
    *, sequence: int, priority: int, eligible: tuple[int, ...] = (0,)
) -> QueuedLifecycleEvent:
    return QueuedLifecycleEvent(
        sequence,
        lifecycle_event(sequence),
        LifecycleExportPolicy("invocation", "debug", priority),
        eligible,
    )


def queued_sequence(event: QueuedLifecycleEvent | None) -> int | None:
    return getattr(event, "sequence", None)
