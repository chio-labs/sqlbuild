"""Render parameterized inspection SQL as readable diagnostic text."""

from __future__ import annotations


def render_inspection_sql(*, query: str, params: tuple[object, ...]) -> str:
    """Inline ``%s`` parameters as quoted literals for display only; never execute the result."""

    parts: list[str] = query.split("%s")
    if len(parts) != len(params) + 1:
        return query
    rendered: list[str] = [parts[0]]
    value: object
    part: str
    for value, part in zip(params, parts[1:], strict=True):
        rendered.append("'" + str(value).replace("'", "''") + "'")
        rendered.append(part)
    return "".join(rendered)
