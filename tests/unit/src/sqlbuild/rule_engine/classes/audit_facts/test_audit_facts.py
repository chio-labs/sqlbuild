from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompiledAudit, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredAuditBlock, DiscoveredAuditFile
from sqlbuild.rule_engine.classes.audit_facts import AuditFacts
from sqlbuild.rule_engine.models import Model
from tests.unit.src.sqlbuild.rule_engine.main.evaluate.helpers import build_project


def test_given_attached_and_project_audits_when_querying_model_then_returns_only_attached_audits() -> (
    None
):
    attached: CompiledAudit = _audit(name="order_amount", attached_target_name="orders")
    other_model: CompiledAudit = _audit(name="customer_status", attached_target_name="customers")
    project_audit: CompiledAudit = _audit(name="inventory_balance", attached_target_name=None)
    project = replace(
        build_project(
            name="orders",
            relative_path="models/orders.sql",
            sql="SELECT 1 AS order_id",
            config_values={},
        ),
        audits=(attached, other_model, project_audit),
    )

    facts = AuditFacts(project=project)

    assert facts.for_model(
        Model(name="orders", path=Path("models/orders.sql"), materialization="view")
    ) == (attached,)
    assert facts.all() == (attached, other_model, project_audit)


def _audit(*, name: str, attached_target_name: str | None) -> CompiledAudit:
    relative_path: Path = Path(f"audits/{name}.sql")
    audit_file = DiscoveredAuditFile(
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


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
