from dataclasses import dataclass

from sqlbuild.adapter.shared.models import LifeCycleEvent


@dataclass(frozen=True)
class StatementRecorderTestCase:
    description: str
    statements: tuple[str, ...]
    expected_snapshot: tuple[LifeCycleEvent, ...]
