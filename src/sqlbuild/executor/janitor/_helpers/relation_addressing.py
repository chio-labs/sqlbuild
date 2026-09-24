"""Janitor guards for relation names that are safe to address unquoted."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from sqlbuild.executor.janitor.constants import (
    CASE_COLLISION_REASON,
    UNQUOTED_ADDRESSING_REASON,
)

_PLAIN_LOWERCASE_IDENTIFIER_RE: re.Pattern[str] = re.compile(r"^[a-z_][a-z0-9_$]*$")


def case_colliding_names(names: Iterable[str]) -> frozenset[str]:
    """Return case-folded names shared by more than one relation in a listing."""

    counts: Counter[str] = Counter(name.lower() for name in names)
    return frozenset(name for name, count in counts.items() if count > 1)


def unaddressable_relation_reason(*, name: str, colliding_names: frozenset[str]) -> str | None:
    """Return why the janitor must not rename or drop a relation by its catalog name."""

    if _PLAIN_LOWERCASE_IDENTIFIER_RE.fullmatch(name) is None:
        return UNQUOTED_ADDRESSING_REASON
    return case_collision_reason(name=name, colliding_names=colliding_names)


def case_collision_reason(*, name: str, colliding_names: frozenset[str]) -> str | None:
    """Return why a relation whose folded name is shared in its listing must not be dropped."""

    if name.lower() in colliding_names:
        return CASE_COLLISION_REASON
    return None
