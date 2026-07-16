"""Public adapter relation type normalization operation."""

from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.type_system._helpers.relation_type import (
    normalize_relation_type as _normalize_relation_type,
)


def normalize_relation_type(value: str) -> RelationType:
    """Normalize warehouse relation type strings into framework categories."""

    return _normalize_relation_type(value)
