"""The process-wide record of connections a deadline interrupted."""

from sqlbuild.runtime.execution_limits.classes.interrupted_connections import (
    InterruptedConnections,
)

interrupted_connections: InterruptedConnections = InterruptedConnections()
