from dataclasses import dataclass

from sqlbuild.adapter.contract.models import LifeCycleEvent


@dataclass(frozen=True)
class StatementRecorderTestCase:
    description: str
    statements: tuple[str, ...]
    log_message: str
    expected_snapshot: tuple[LifeCycleEvent, ...]
