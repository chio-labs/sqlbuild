from collections.abc import Callable
from typing import overload

@overload
def audit_factory[FunctionT: Callable[..., object]](function: FunctionT) -> FunctionT: ...
@overload
def audit_factory[FunctionT: Callable[..., object]](
    function: None = None,
) -> Callable[[FunctionT], FunctionT]: ...
