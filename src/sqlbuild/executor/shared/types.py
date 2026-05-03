"""Executor domain types."""

from __future__ import annotations

from enum import StrEnum


class TablePromotionMode(StrEnum):
    DIRECT = "direct"
    STAGED = "staged"


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionPhase(StrEnum):
    PRE_HOOK = "pre_hook"
    STAGING = "staging"
    SCHEMA_CHANGE = "schema_change"
    TYPE_ENFORCEMENT = "type_enforcement"
    AUDIT = "audit"
    PROMOTION = "promotion"
    DML = "dml"
    POST_HOOK = "post_hook"
    FINGERPRINT = "fingerprint"
    CUSTOM_MATERIALIZATION = "custom_materialization"
