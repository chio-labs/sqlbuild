"""Type declarations for runtime observability contracts."""

from collections.abc import Mapping

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | tuple[JSONValue, ...] | Mapping[str, JSONValue]
