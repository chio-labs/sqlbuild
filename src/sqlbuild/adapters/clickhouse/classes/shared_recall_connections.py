"""The process's open Recall store connections, shared by every handle native code holds."""

from __future__ import annotations

from typing import ClassVar

from sqlbuild.adapters.clickhouse.classes.recall_connections import RecallConnections


class SharedRecallConnections:
    """The one registry of open Recall store connections in this process."""

    connections: ClassVar[RecallConnections] = RecallConnections()
