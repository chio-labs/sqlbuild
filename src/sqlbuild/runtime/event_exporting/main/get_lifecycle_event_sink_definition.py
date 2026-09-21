"""Read lifecycle-event sink declarations."""

from collections.abc import Callable

from sqlbuild.python_nodes.main.read_attached_definition import read_attached_definition
from sqlbuild.runtime.event_exporting.constants import LIFECYCLE_EVENT_SINK_ATTRIBUTE
from sqlbuild.runtime.event_exporting.models import LifecycleEventSinkDefinition


def get_lifecycle_event_sink_definition(
    function: Callable[..., object],
) -> LifecycleEventSinkDefinition | None:
    """Return lifecycle-event sink metadata attached to a function."""

    return read_attached_definition(
        function=function,
        attribute_name=LIFECYCLE_EVENT_SINK_ATTRIBUTE,
        definition_type=LifecycleEventSinkDefinition,
    )
