"""Describe literal SQL that still reads a renamed model through its old name."""

from __future__ import annotations


def old_name_reference_message(
    *, owner_label: str, written: str, method: str, model_name: str
) -> str:
    """Return the P008 message for SQL naming a relation kept only as a compatibility view."""

    return (
        f"{owner_label} names '{written}' in SQL passed to ctx.{method}(); it is the old name "
        f"of model:{model_name}, kept only as a compatibility view for consumers outside the "
        "project"
    )
