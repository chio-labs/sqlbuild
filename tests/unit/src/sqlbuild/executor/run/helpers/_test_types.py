from dataclasses import dataclass

from sqlbuild.adapter.shared.models import LifeCycleEvent


@dataclass(frozen=True)
class BuildQualifiedNameTestCase:
    description: str
    database: str | None
    schema: str | None
    name: str
    expected_qualified: str


@dataclass(frozen=True)
class BuildFailedResultTestCase:
    description: str
    recorded_statements: tuple[str, ...]
    warning_messages: tuple[str, ...]
    expected_model_name: str
    expected_error_message: str
    expected_lifecycle_events: tuple[LifeCycleEvent, ...]
