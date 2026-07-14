"""Public adapter type comparison operation."""

from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.adapter.type_system._helpers.type_normalization import types_equal as _types_equal


def types_equal(*, left: str, right: str, dialect: TypeDialect | str | None) -> bool:
    """Return whether two type strings are semantically equivalent."""

    return _types_equal(left=left, right=right, dialect=dialect)
