"""Capture fragments for discovery coverage tests."""

from __future__ import annotations

import dataclasses

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs

_VALUE_KIND: str = "sqlbuild.sql_values.types:SqlValueKind"


def constant_declaration(*, kind: str, value: object) -> dict[str, object]:
    """Return one captured constant declaration of a logical kind."""

    return {
        "value": {"logical_type": {"kind": {"__enum__": f"{_VALUE_KIND}.{kind}"}}, "value": value}
    }


def empty_inputs_capture(**overrides: object) -> dict[str, object]:
    """Return a capture with every `DiscoveredProjectInputs` field, in order, then overrides."""

    return {
        "__type__": "sqlbuild.compiler.discovery.models:DiscoveredProjectInputs",
        **{field.name: [] for field in dataclasses.fields(DiscoveredProjectInputs)},
        **overrides,
    }
