"""Shapes the native model config bindings return."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn

type NativeHeaderMetadataRow = tuple[
    tuple[SchemaColumn, ...] | _native.NativeConfigError,
    tuple[SchemaAuditInstance, ...] | _native.NativeConfigError | None,
]
