"""Relation location qualification entrypoint."""

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relation_naming.helpers.naming import (
    resolve_relation_location_qualified_name_impl,
)
from sqlbuild.adapter.relation_naming.types import RelationLocation


def resolve_relation_location_qualified_name(
    *, adapter: BaseAdapter, location: RelationLocation
) -> str:
    """Resolve a structural relation location through adapter qualification."""

    return resolve_relation_location_qualified_name_impl(adapter=adapter, location=location)
