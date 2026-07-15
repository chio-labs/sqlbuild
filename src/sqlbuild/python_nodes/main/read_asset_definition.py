"""Read SQLBuild asset metadata from a Python function."""

from collections.abc import Callable

from sqlbuild.python_nodes._helpers.attachment import read_attached_definition
from sqlbuild.python_nodes.models import AssetDefinition


def read_asset_definition(function: Callable[..., object]) -> AssetDefinition | None:
    """Return SQLBuild asset metadata from a decorated function, if present."""

    return read_attached_definition(
        function=function,
        attribute_name="__sqlbuild_asset__",
        definition_type=AssetDefinition,
    )
