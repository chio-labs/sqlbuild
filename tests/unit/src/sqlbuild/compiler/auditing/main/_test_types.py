from dataclasses import dataclass, field

from sqlbuild.compiler.auditing.types import AuditAttachmentKind, AuditRunScope, AuditSeverity


@dataclass(frozen=True)
class RenderAuditSqlTestCase:
    description: str
    unresolved_sql: str
    model_locations: dict[str, str]
    source_map_entries: dict[str, tuple[str | None, str | None, str | None]]
    expected_sql_fragment: str
    relation_overrides: dict[str, str] = field(default_factory=dict)
    seed_locations: dict[str, str] = field(default_factory=dict)
    adapter_name: str | None = None


@dataclass(frozen=True)
class AuditGateIdentityTestCase:
    description: str
    prod_resolved_sql: str
    dev_resolved_sql: str
    unresolved_sql: str
    expected_definition_equal: bool
    expected_execution_equal: bool
    expected_binding_set_equal: bool
    dev_attached_column_name: str | None = None
    severity: AuditSeverity = AuditSeverity.ERROR


@dataclass(frozen=True)
class AuditGateAggregateIdentityTestCase:
    description: str
    expected_binding_set_equal: bool
    expected_blocking_set_equal: bool


@dataclass(frozen=True)
class AuditGateSingleFieldIdentityTestCase:
    description: str
    left_unresolved_sql: str
    left_resolved_sql: str
    right_unresolved_sql: str
    right_resolved_sql: str
    expected_definition_equal: bool
    expected_execution_equal: bool
    left_run_scope: AuditRunScope = AuditRunScope.FINAL
    right_run_scope: AuditRunScope = AuditRunScope.FINAL
    left_attachment_kind: AuditAttachmentKind = AuditAttachmentKind.MODEL
    right_attachment_kind: AuditAttachmentKind = AuditAttachmentKind.MODEL
    left_always_run: bool = False
    right_always_run: bool = False


@dataclass(frozen=True)
class ParseAuditInstanceTestCase:
    description: str
    raw_audit: object
    expected_definition_name: str
    expected_always_run: bool
    expected_argument_keys: tuple[str, ...]


@dataclass(frozen=True)
class ParseAuditInstanceErrorTestCase:
    description: str
    raw_audit: object
    expected_error_fragment: str
