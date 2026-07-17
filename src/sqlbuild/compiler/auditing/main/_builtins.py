"""Built-in generic audit definitions."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from sqlbuild.compiler.auditing.constants import (
    BUILT_IN_AUDIT_NAMES,
    BUILT_IN_AUDIT_SHADOW_CODE,
)
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.discovery.models import DiscoveredAuditBlock, DiscoveredAuditFile


def build_builtin_audit_resolution(
    project_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]],
) -> tuple[
    dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]],
    tuple[CompilerDiagnostic, ...],
]:
    """Return built-in-aware generic audit definitions and shadow diagnostics."""

    merged: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]] = {
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
    merged.update(project_definitions)
    return merged, _build_builtin_audit_shadow_diagnostics(project_definitions)


def _build_builtin_audit_shadow_diagnostics(
    project_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]],
) -> tuple[CompilerDiagnostic, ...]:
    """Build warnings for project generic audits that override built-ins."""

    diagnostics: list[CompilerDiagnostic] = []
    definition_name: str
    definition: tuple[DiscoveredAuditFile, DiscoveredAuditBlock]
    for definition_name, definition in sorted(project_definitions.items()):
        if definition_name not in BUILT_IN_AUDIT_NAMES:
            continue
        diagnostics.append(
            CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity.WARNING,
                code=BUILT_IN_AUDIT_SHADOW_CODE,
                message=(
                    f"project audit '{definition_name}' overrides built-in audit "
                    f"'{definition_name}'"
                ),
                path=definition[0].relative_path,
                help="rename the project audit if this override is unintended",
            )
        )
    return tuple(diagnostics)


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
