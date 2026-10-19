"""The logical relation behind each SQLite table name this adapter rendered."""

from __future__ import annotations

import threading

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.sqlite.constants import RELATION_NAME_COLLISION_CODE


class LogicalRelations:
    """Map table names to the (schema, name) they were rendered for, refusing collisions."""

    def __init__(self) -> None:
        self._by_physical: dict[str, tuple[str, str]] = {}
        self._guard: threading.Lock = threading.Lock()

    def remember(self, *, schema: str, name: str, physical: str) -> None:
        """Record one rendering; a second relation stored under the same table name is refused."""

        with self._guard:
            existing: tuple[str, str] = self._by_physical.setdefault(
                physical.lower(), (schema, name)
            )
        if (existing[0].lower(), existing[1].lower()) == (schema.lower(), name.lower()):
            return
        raise AdapterUserError(
            message=(
                f"SQLite relations '{existing[0]}.{existing[1]}' and '{schema}.{name}' would both "
                f"be stored as table '{physical}'"
            ),
            code=RELATION_NAME_COLLISION_CODE,
            help=(
                "SQLite stores schema relations as '<schema>__<name>' in one file. Rename one of "
                "the relations, or move it to a schema whose name it does not start with."
            ),
        )

    def lookup(self, physical: str) -> tuple[str, str] | None:
        """Return the rendered (schema, name) of one physical table name, if known."""

        with self._guard:
            return self._by_physical.get(physical.lower())
