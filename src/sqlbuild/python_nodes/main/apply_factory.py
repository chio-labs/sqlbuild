"""Apply SQLBuild factory metadata to a Python function."""

from collections.abc import Callable
from typing import Any, cast

from sqlbuild.python_nodes._helpers.attachment import attach_definition
from sqlbuild.python_nodes.models import FactoryDefinition


def apply_factory(function: Callable[..., object]) -> Callable[..., object]:
    """Apply SQLBuild factory metadata to a Python function."""

    factory_function: Any = cast(Any, function)
    return attach_definition(
        function=function,
        attribute_name="__sqlbuild_factory__",
        definition=FactoryDefinition(name=factory_function.__name__),
    )
