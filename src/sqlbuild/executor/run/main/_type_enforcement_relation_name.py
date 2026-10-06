"""Public name of the relation type enforcement rebuilds a staging table into."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.run._helpers.validation.type_enforcement import (
    type_enforcement_relation_name,
)


def resolve_type_enforcement_relation_name(*, adapter: BaseAdapter, staging_table: str) -> str:
    """Return the fitted relation name type enforcement rebuilds a staging table into."""

    return type_enforcement_relation_name(adapter=adapter, staging_table=staging_table)
