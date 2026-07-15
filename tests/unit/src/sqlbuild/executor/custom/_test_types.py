from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.executor.custom.models import MaterializationContext, PrepareVersionContext


@dataclass(frozen=True)
class CustomContextExecutionTestCase:
    description: str
    context_builder: Callable[..., MaterializationContext | PrepareVersionContext]
    sql: str
    expected_result: object
    expected_operation_order: tuple[str, ...]
    expected_recorded_sql: str


@dataclass(frozen=True)
class CustomContextQualificationTestCase:
    description: str
    context_builder: Callable[..., MaterializationContext | PrepareVersionContext]
    name: str
    database: str | None
    schema: str | None
    expected_qualified_name: str
