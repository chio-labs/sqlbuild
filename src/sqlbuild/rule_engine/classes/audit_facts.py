"""Audit facts for custom rules."""

from functools import cached_property

from sqlbuild._native import (
    CompiledAudit,
    Model,
    compiled_audit_record,
)
from sqlbuild.rule_engine.types import RuleFactProject


class AuditFacts:
    """Compiled audits indexed by their model subject."""

    def __init__(self, *, project: RuleFactProject) -> None:
        self._project: RuleFactProject = project

    @cached_property
    def _audits(self) -> tuple[CompiledAudit, ...]:
        return tuple(map(compiled_audit_record, self._project.audits))

    @cached_property
    def _by_model(self) -> dict[str, tuple[CompiledAudit, ...]]:
        by_model: dict[str, list[CompiledAudit]] = {}
        for audit in self._audits:
            if audit.attached_target_name is not None:
                by_model.setdefault(audit.attached_target_name, []).append(audit)
        return {name: tuple(audits) for name, audits in by_model.items()}

    def all(self) -> tuple[CompiledAudit, ...]:
        return self._audits

    def for_model(self, model: Model) -> tuple[CompiledAudit, ...]:
        return self._by_model.get(model.name, ())
