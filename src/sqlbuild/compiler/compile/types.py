"""Compile domain types."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from sqlbuild.sql_values.models import SqlValue


class TypedSqlValueRenderer(Protocol):
    """Adapter rendering operations consumed by authored SQL expansion."""

    adapter_name: str

    def render_typed_scalar(self, *, value: SqlValue) -> str: ...

    def render_typed_value_list(self, *, value: SqlValue) -> str: ...

    def render_typed_array(self, *, value: SqlValue) -> str: ...

    def render_typed_object(self, *, value: SqlValue) -> str: ...


class AttachedAuditTargetKind(StrEnum):
    MODEL = "model"
    SOURCE = "source"


class CompileContextKey(StrEnum):
    RUN_ID = "run.id"
    RUN_TARGET = "run.target"
    MODEL_NAME = "model.name"
    MODEL_DATABASE = "model.database"
    MODEL_SCHEMA = "model.schema"
    MODEL_ALIAS = "model.alias"
    DESTINATION_DATABASE = "destination.database"
    DESTINATION_SCHEMA = "destination.schema"
    DESTINATION_TABLE = "destination.table"
    DESTINATION_QUALIFIED = "destination.qualified"


class TemplateNamespace(StrEnum):
    ENV = "ENV"
    CTX = "CTX"


class CompiledResourceType(StrEnum):
    MODEL = "model"
    SOURCE = "source"
    SEED = "seed"
    UDF = "udf"
    TABLE_FN = "table_fn"
    DBT_REF = "dbt_ref"
    AUDIT = "audit"
    SQL_TEST = "sql_test"
    SQL_SCENARIO = "sql_scenario"


class DiagnosticPhase(StrEnum):
    """Phase that produced a compiler diagnostic."""

    COMPILE = "compile"
    CONTRACT = "contract"
    PLAN = "plan"
    BUILD = "build"
    AUDIT = "audit"
    TEST = "test"
    CONNECTION = "connection"


class DiagnosticSeverity(StrEnum):
    """Severity for a compiler diagnostic."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FunctionLanguage(StrEnum):
    SQL = "sql"
    PYTHON = "python"


class SqlTestMode(StrEnum):
    MODEL = "model"
    MACRO = "macro"
    UDF = "udf"
    TABLE_FN = "table_fn"
