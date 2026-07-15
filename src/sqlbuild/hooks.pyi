from collections.abc import Callable
from typing import overload

from sqlbuild.executor.run.models import HookContext as HookContext
from sqlbuild.executor.run.models import HookSkipResult as HookSkipResult
from sqlbuild.python_nodes.models import HookDefinition as HookDefinition

__all__ = ("HookContext", "HookDefinition", "HookSkipResult", "get_hook_definition", "hook")

@overload
def hook(function: Callable[..., object]) -> Callable[..., object]: ...
@overload
def hook(
    *, name: str | None = None, description: str | None = None
) -> Callable[[Callable[..., object]], Callable[..., object]]: ...
def get_hook_definition(function: Callable[..., object]) -> HookDefinition | None: ...
