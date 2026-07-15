from collections.abc import Callable, Sequence
from typing import overload

from sqlbuild.compiler.python_nodes.types import SkipMode as SkipMode
from sqlbuild.executor.python_nodes.models import TaskContext as TaskContext
from sqlbuild.python_nodes.models import RetryPolicy, SqlResourceRef, TaskDefinition

__all__ = ("SkipMode", "TaskContext", "get_task_definition", "task")

@overload
def task(function: Callable[..., object]) -> Callable[..., object]: ...
@overload
def task(
    *,
    name: str | None = None,
    depends_on: Callable[..., object]
    | SqlResourceRef
    | tuple[Callable[..., object] | SqlResourceRef, ...]
    | list[Callable[..., object] | SqlResourceRef] = (),
    tags: Sequence[str] = (),
    group: str | None = None,
    description: str | None = None,
    meta: dict[str, object] | None = None,
    retry: RetryPolicy | None = None,
) -> Callable[[Callable[..., object]], Callable[..., object]]: ...
def get_task_definition(function: Callable[..., object]) -> TaskDefinition | None: ...
