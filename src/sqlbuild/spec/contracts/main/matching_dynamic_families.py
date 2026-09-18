"""Public compiler entry point for dynamic-family name matching."""

from sqlbuild.spec.contracts._helpers.dynamic_columns import matching_dynamic_families as _match
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily


def matching_dynamic_families(
    *, families: tuple[SchemaDynamicColumnFamily, ...], column_name: str
) -> tuple[SchemaDynamicColumnFamily, ...]:
    """Return declared dynamic families accepting a physical column name."""

    return _match(families=families, column_name=column_name)
