from dataclasses import dataclass


@dataclass(frozen=True)
class AuditFactsTestCase:
    description: str
    attached_name: str
    other_model_name: str
    project_audit_name: str
    expected_attached_names: tuple[str, ...]
    expected_all_names: tuple[str, ...]
