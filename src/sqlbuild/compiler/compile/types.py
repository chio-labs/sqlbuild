"""Compile domain types."""

from __future__ import annotations

from enum import StrEnum


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
    TARGET_DATABASE = "target.database"
    TARGET_SCHEMA = "target.schema"
    TARGET_TABLE = "target.table"
    TARGET_QUALIFIED = "target.qualified"


class TemplateNamespace(StrEnum):
    ENV = "ENV"
    CTX = "CTX"


class CompiledResourceType(StrEnum):
    MODEL = "model"
    SOURCE = "source"
    SEED = "seed"
    FUNCTION = "function"
    DBT_REF = "dbt_ref"
    AUDIT = "audit"
    SQL_TEST = "sql_test"
    SQL_SCENARIO = "sql_scenario"


class FunctionLanguage(StrEnum):
    SQL = "sql"
    PYTHON = "python"


class SqlTestMode(StrEnum):
    MODEL = "model"
    MACRO = "macro"
    UDF = "udf"
    TABLE_FN = "table_fn"
