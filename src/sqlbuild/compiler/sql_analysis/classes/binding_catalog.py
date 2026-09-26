"""Compile-lifetime ownership of the native binding catalog."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import copy
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.sql_analysis.constants import (
    CASE_SENSITIVE_BINDING_DIALECTS,
    SQL_QUOTED_IDENTIFIER_DELIMITER,
)
from sqlbuild.compiler.sql_analysis.models import SqlSchemaValidationRequest
from sqlbuild.compiler.sql_analysis.types import (
    NativeBindingRequest,
    NativeCatalogModule,
    NativeProjectCatalog,
)


class BindingCatalog:
    def __init__(
        self,
        *,
        dialect: str,
        quoted_ignore_case: bool,
        known_functions: tuple[str, ...],
        known_types: tuple[str, ...],
        relations: Mapping[str, Mapping[str, str]],
    ) -> None:
        self.schemas: dict[str, Mapping[str, str]] = dict(relations)
        self.dialect: str = dialect
        self.quoted_ignore_case: bool = quoted_ignore_case
        self.analysis_shapes: dict[str, tuple[Mapping[str, str], Mapping[str, str]]] = {}
        self.native: NativeProjectCatalog = cast(NativeCatalogModule, _native).ProjectCatalog(
            {
                "dialect": dialect,
                "quoted_ignore_case": quoted_ignore_case,
                "known_functions": known_functions,
                "known_types": known_types,
                "relations": relations,
            }
        )

    def prepare_analysis(
        self,
        *,
        types: Mapping[str, Mapping[str, str]],
        nullability: Mapping[str, Mapping[str, str]],
    ) -> None:
        updates: dict[str, tuple[Mapping[str, str], Mapping[str, str]]] = {}
        for name, columns in nullability.items():
            shape: tuple[Mapping[str, str], Mapping[str, str]] = (types.get(name, {}), columns)
            if self.analysis_shapes.get(name) != shape:
                updates[name] = shape
                self.analysis_shapes[name] = shape
        if updates:
            self.native.update_analysis(updates)

    def with_relations(self, relations: Mapping[str, Mapping[str, str]]) -> BindingCatalog:
        catalog: BindingCatalog = copy(self)
        catalog.schemas = {**self.schemas, **relations}
        catalog.analysis_shapes = dict(self.analysis_shapes)
        catalog.native = self.native.with_relations(relations)
        return catalog

    def inferred_schema(
        self, *, sql: str, columns: dict[str, str], inputs: Mapping[str, Mapping[str, str]]
    ) -> dict[str, str]:
        if self.quoted_ignore_case or self.dialect not in CASE_SENSITIVE_BINDING_DIALECTS:
            return columns
        has_exact_input: bool = False
        for shape in inputs.values():
            if any(SQL_QUOTED_IDENTIFIER_DELIMITER in name for name in shape):
                has_exact_input = True
                break
        if SQL_QUOTED_IDENTIFIER_DELIMITER not in sql and not has_exact_input:
            return columns
        return self.native.inferred_schema(sql=sql, columns=columns, inputs=inputs)

    def prepare(self, requests: Sequence[SqlSchemaValidationRequest]) -> list[NativeBindingRequest]:
        additions: dict[str, Mapping[str, str]] = {}
        for request in requests:
            for name, columns in request.schema.items():
                if columns and name not in self.schemas:
                    additions[name] = columns
                    self.schemas[name] = columns
        if additions:
            self.native.update_relations(additions)
        prepared: list[NativeBindingRequest] = []
        for request in requests:
            overrides: dict[str, Mapping[str, str]] = {
                name: columns
                for name, columns in request.schema.items()
                if columns and self.schemas.get(name) != columns
            }
            prepared.append(
                (
                    request.sql,
                    [(name, bool(request.schema[name])) for name in sorted(request.schema)],
                    overrides,
                )
            )
        return prepared
