"""Compile domain types."""

from __future__ import annotations

from enum import StrEnum


class SqlReferenceKind(StrEnum):
    REF = "ref"
    SOURCE = "source"
    DBT_REF = "dbt_ref"


class AttachedAuditTargetKind(StrEnum):
    MODEL = "model"
    SOURCE = "source"


class CompileContextKey(StrEnum):
    RUN_ID = "run.id"
    RUN_ENVIRONMENT = "run.environment"
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
