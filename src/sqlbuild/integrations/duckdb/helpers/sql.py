"""DuckDB-specific SQL helpers."""

from __future__ import annotations


def build_attach_sql(attach_entry: dict[str, object]) -> str:
    """Build an ATTACH statement from one attach config entry."""

    path: str = str(attach_entry["path"])
    sql: str = f"ATTACH '{path}'"
    alias: object | None = attach_entry.get("alias")
    if alias is not None:
        sql += f" AS {alias}"
    options: list[str] = []
    attach_type: object | None = attach_entry.get("type")
    if attach_type is not None:
        options.append(f"TYPE {attach_type}")
    read_only: object | None = attach_entry.get("read_only")
    if read_only is True:
        options.append("READ_ONLY")
    if options:
        sql += f" ({', '.join(options)})"
    return sql
