"""Describe literal SQL that still reads a renamed model through its old name."""

from __future__ import annotations

import sqlbuild._native as _native


def old_name_reference_message(
    *, owner_label: str, written: str, method: str, model_name: str
) -> str:
    """Return the P008 message for SQL naming a relation kept only as a compatibility view."""

    return _native.old_name_reference_message(owner_label, written, method, model_name)
