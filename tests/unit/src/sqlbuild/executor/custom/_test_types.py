from collections.abc import Callable
from dataclasses import dataclass

from sqlbuild.executor.custom.models import MaterializationContext


@dataclass(frozen=True)
class CustomContextExecutionTestCase:
    description: str
    context_builder: Callable[..., MaterializationContext]
    sql: str
    expected_result: object
    expected_operation_order: tuple[str, ...]
    expected_recorded_sql: str


@dataclass(frozen=True)
class CustomContextQualificationTestCase:
    description: str
    context_builder: Callable[..., MaterializationContext]
    name: str
    database: str | None
    schema: str | None
    expected_qualified_name: str
