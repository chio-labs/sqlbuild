"""One canonical JSON text per JSON value, so equal values compare equal as text."""

from __future__ import annotations

import json
from decimal import Decimal


def canonical_json(text: str | None) -> str | None:
    """`text` as JSON with sorted keys, no whitespace and numbers in their shortest exact form."""

    if text is None:
        return None
    return _canonical(json.loads(text, parse_float=Decimal, parse_int=Decimal))


def _canonical(value: object) -> str:
    if isinstance(value, dict):
        members: list[str] = [
            f"{json.dumps(key, ensure_ascii=False)}:{_canonical(value[key])}"
            for key in sorted(value)
        ]
        return "{" + ",".join(members) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if isinstance(value, Decimal):
        return _canonical_number(value)
    return json.dumps(value, ensure_ascii=False)


def _canonical_number(number: Decimal) -> str:
    if number.is_finite() and number == number.to_integral_value():
        return str(int(number))
    return format(number.normalize(), "f")
