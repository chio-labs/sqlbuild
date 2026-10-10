"""Data the native model loop hands its Python callbacks."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    ExpansionSpan,
    MacroExpansionResult,
)
from sqlbuild.compiler.scopes.models import UsageRecord
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn


@dataclass(frozen=True)
class PlainModelFacts:
    """What the native loop finished for one model: config, references, query and description."""

    config: CompileModelConfig
    values: dict[str, object]
    references: list[tuple[str, str, str | None, int | None]]
    query_sql: str
    description: str | None
    schema: tuple[tuple[SchemaColumn, ...], tuple[SchemaAuditInstance, ...], bool] | None
    declaration_sql: str
    declaration_spans: tuple[ExpansionSpan, ...]
    declaration_usages: tuple[UsageRecord, ...]
    macro_expansion: MacroExpansionResult | None
