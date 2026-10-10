"""Row shapes the native model loop hands its Python host."""

from sqlbuild.spec.contracts.models import (
    SchemaAuditInstance,
    SchemaColumn,
    SchemaDynamicColumnFamily,
)

type PlainSchemaRow = tuple[
    tuple[SchemaColumn, ...],
    tuple[SchemaAuditInstance, ...],
    bool,
    tuple[SchemaDynamicColumnFamily, ...],
    str | None,
]

type ReferenceRow = tuple[str, str, str | None, int | None]
type SpanRow = tuple[int, int, int, int]
