"""Relation location qualification entrypoint."""

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations._helpers.naming import (
    resolve_relation_location_qualified_name_impl,
)
from sqlbuild.adapter.relations.types import RelationLocation


def resolve_relation_location_qualified_name(
    *, adapter: BaseAdapter, location: RelationLocation
) -> str:
    """Resolve a structural relation location through adapter qualification."""

    return resolve_relation_location_qualified_name_impl(adapter=adapter, location=location)
