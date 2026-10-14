"""Plain-data rows exchanged with the native project assembly."""

from __future__ import annotations

type ObjectKeyRow = tuple[str, str]
type NamespaceRow = tuple[str | None, str | None, str | None, str | None]
