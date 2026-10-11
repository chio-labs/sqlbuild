"""Built-in generic audit definitions."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from sqlbuild.compiler.discovery.models import DiscoveredAuditBlock, DiscoveredAuditFile


def builtin_audit_definitions() -> tuple[DiscoveredAuditFile, ...]:
    """Every built-in generic audit definition, which project definitions override by name."""

    definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]] = {
        "accepted_values": _build_audit_definition(
            name="accepted_values",
            sql_body=dedent(
                """\
                SELECT @column
                FROM @relation
                WHERE @column IS NOT NULL
                  AND @column NOT IN (@'values')
                """
            ).strip(),
        ),
        "not_null": _build_audit_definition(
            name="not_null",
            sql_body=dedent(
                """\
                SELECT @column
                FROM @relation
                WHERE @column IS NULL
                """
            ).strip(),
        ),
        "relationships": _build_audit_definition(
            name="relationships",
            sql_body=dedent(
                """\
                SELECT @column
                FROM @relation
                WHERE @column IS NOT NULL
                  AND @column NOT IN (
                    SELECT @field
                    FROM @to
                    WHERE @field IS NOT NULL
                  )
                """
            ).strip(),
        ),
        "unique": _build_audit_definition(
            name="unique",
            sql_body=dedent(
                """\
                SELECT @column, COUNT(*) AS duplicate_count
                FROM @relation
                WHERE @column IS NOT NULL
                GROUP BY @column
                HAVING COUNT(*) > 1
                """
            ).strip(),
        ),
    }
    return tuple(audit_file for audit_file, _ in definitions.values())


def _build_audit_definition(
    *, name: str, sql_body: str
) -> tuple[DiscoveredAuditFile, DiscoveredAuditBlock]:
    relative_path: Path = Path("audits/generic") / f"{name}.sql"
    contents: str = f"AUDIT ();\n\n{sql_body}\n"
    block: DiscoveredAuditBlock = DiscoveredAuditBlock(
        audit_index=0,
        header_values={},
        sql_body=sql_body,
    )
    audit_file: DiscoveredAuditFile = DiscoveredAuditFile(
        file_path=Path("<built-in>") / relative_path,
        relative_path=relative_path,
        contents=contents,
        blocks=(block,),
    )
    return audit_file, block
