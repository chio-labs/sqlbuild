"""Audit facts for custom rules."""

from sqlbuild.compiler.compile.models import CompiledAudit, CompiledProject
from sqlbuild.rule_engine.models import Model


class AuditFacts:
    """Compiled audits indexed by their model subject."""

    def __init__(self, *, project: CompiledProject) -> None:
        self._audits: tuple[CompiledAudit, ...] = project.audits

    def all(self) -> tuple[CompiledAudit, ...]:
        return self._audits

    def for_model(self, model: Model) -> tuple[CompiledAudit, ...]:
        return tuple(audit for audit in self._audits if audit.attached_target_name == model.name)
