"""The process-wide record of connections running a statement, so a termination can cancel them."""

from sqlbuild.runtime.execution_limits.classes.active_connections import ActiveConnections

running_statements: ActiveConnections = ActiveConnections()
