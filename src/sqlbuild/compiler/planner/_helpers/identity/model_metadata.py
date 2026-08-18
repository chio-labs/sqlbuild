"""Model contract metadata used by version identity."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.discovery.models import EnumDeclaration
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.spec.contracts.models import SchemaColumn, SchemaModelEntry


def contract_output_signature(*, model: CompiledModel) -> dict[str, object] | None:
    """Build the enforced contract portion of a model's execution identity."""

    if model.config.values.get("contract") != ContractPolicy.ENFORCED:
        return None
    schema_entry: SchemaModelEntry | None = model.schema_entry
    if schema_entry is None or not schema_entry.columns:
        return None
    return {
        "enforced": True,
        "columns": [
            _column_output_signature(model=model, column=column) for column in schema_entry.columns
        ],
    }


def _column_output_signature(*, model: CompiledModel, column: SchemaColumn) -> dict[str, object]:
    signature: dict[str, object] = {
        "name": column.name,
        "type": column.type,
        "nullable": column.nullable,
    }
    enum_declaration: EnumDeclaration | None = model.enum_columns.get(column.name)
    if enum_declaration is not None:
        signature["enum"] = {
            "name": enum_declaration.name,
            "members": [
                {"name": member.name, "value": member.value} for member in enum_declaration.members
            ],
        }
    return signature
