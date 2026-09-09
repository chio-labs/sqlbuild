from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledAudit, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredAuditBlock, DiscoveredAuditFile


def build_audit(*, name: str, attached_target_name: str | None) -> CompiledAudit:
    relative_path: Path = Path(f"audits/{name}.sql")
    audit_file: DiscoveredAuditFile = DiscoveredAuditFile(
        file_path=relative_path,
        relative_path=relative_path,
        contents="",
        blocks=(),
    )
    return CompiledAudit(
        key=CompiledObjectKey(CompiledResourceType.AUDIT, name),
        scope_deps=(),
        name=name,
        definition_name=name,
        audit_file=audit_file,
        audit_block=DiscoveredAuditBlock(audit_index=0, header_values={}, sql_body="SELECT 1"),
        sql_body="SELECT 1",
        attached_target_name=attached_target_name,
    )
