"""Model contract metadata used by version identity."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.discovery.models import EnumDeclaration
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.spec.contracts.models import SchemaColumn, SchemaModelEntry


def contract_output_signature(*, model: CompiledModel) -> dict[str, object] | None:
    """Build required model output metadata that participates in execution identity."""

    schema_entry: SchemaModelEntry | None = model.schema_entry
    if schema_entry is None or not (schema_entry.columns or schema_entry.dynamic_columns):
        return None
    enforced: bool = model.config.values.get("contract") == ContractPolicy.ENFORCED
    if not enforced and schema_entry.model_schema is None:
        return None
    signature: dict[str, object] = {
        "enforced": enforced,
        "columns": [
            _column_output_signature(model=model, column=column) for column in schema_entry.columns
        ],
    }
    if schema_entry.dynamic_columns:
        signature["dynamic_columns"] = [
            {
                "name": family.name,
                "pivot_column": family.pivot_column,
                "value_column": family.value_column,
                "aggregate": family.aggregate,
                "type": family.type,
                "name_pattern": family.name_pattern,
            }
            for family in schema_entry.dynamic_columns
        ]
    return signature


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


def declared_columns_hash(*, model: CompiledModel) -> str:
    """Hash the model's own declared columns, column families, and contract setting."""

    schema_entry: SchemaModelEntry | None = model.schema_entry
    payload: dict[str, object] = {
        "contract": model.config.values.get("contract"),
        "columns": [
            {"name": column.name, "type": column.type, "nullable": column.nullable}
            for column in (schema_entry.columns if schema_entry is not None else ())
        ],
        "dynamic_columns": [
            {
                "name": family.name,
                "pivot_column": family.pivot_column,
                "value_column": family.value_column,
                "aggregate": family.aggregate,
                "type": family.type,
                "name_pattern": family.name_pattern,
            }
            for family in (schema_entry.dynamic_columns if schema_entry is not None else ())
        ],
        "type_enforcement": schema_entry.type_enforcement if schema_entry is not None else None,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
