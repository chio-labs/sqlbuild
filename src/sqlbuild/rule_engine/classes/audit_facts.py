"""Audit facts for custom rules."""

from sqlbuild.compiler.compile.models import CompiledAudit, CompiledProject
from sqlbuild.rule_engine.models import Model


class AuditFacts:
    """Compiled audits indexed by their model subject."""

    def __init__(self, *, project: CompiledProject) -> None:
        self._audits: tuple[CompiledAudit, ...] = project.audits
        by_model: dict[str, list[CompiledAudit]] = {}
        for audit in self._audits:
            if audit.attached_target_name is not None:
                by_model.setdefault(audit.attached_target_name, []).append(audit)
        self._by_model: dict[str, tuple[CompiledAudit, ...]] = {
            name: tuple(audits) for name, audits in by_model.items()
        }

    def all(self) -> tuple[CompiledAudit, ...]:
        return self._audits

    def for_model(self, model: Model) -> tuple[CompiledAudit, ...]:
        return self._by_model.get(model.name, ())
