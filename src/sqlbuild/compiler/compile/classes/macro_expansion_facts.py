"""Facts recorded while expanding the macros of one authored SQL string."""

from __future__ import annotations

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.macro_bridge.constants import ARGUMENT_REFERENCE_EVENT
from sqlbuild.compiler.macro_bridge.types import MacroCallEvent
from sqlbuild.compiler.scopes.models import DeclarationIdentity, UsageRecord
from sqlbuild.python_nodes.models import SqlResourceRef


class MacroExpansionFacts:
    """Facts one authored string's macro expansion records, in encounter order."""

    def __init__(self) -> None:
        self.dependencies: list[DeclarationIdentity] = []
        self.usages: list[UsageRecord] = []
        self.relations: dict[SqlResourceRef, int] = {}
        self.argument_references: dict[SqlResourceRef, None] = {}
        self.call_site_refs: list[set[SqlResourceRef]] = []
        self.rendering_approved: list[frozenset[SqlResourceRef]] = []
        self.event_log: list[MacroCallEvent] | None = None
        self.memo_blocked: bool = False

    def begin_event_log(self) -> MacroExpansionFacts:
        """Start recording the consumer-independent facts of one top-level macro call."""

        self.event_log = []
        self.memo_blocked = False
        return self

    def end_event_log(self) -> tuple[tuple[MacroCallEvent, ...], bool]:
        """Stop recording and return the facts and whether the call may be replayed."""

        events: tuple[MacroCallEvent, ...] = tuple(self.event_log or ())
        self.event_log = None
        return events, not self.memo_blocked

    def note_event(self, event: MacroCallEvent) -> None:
        """Record one fact of the macro call being executed, when recording."""

        if self.event_log is not None:
            self.event_log.append(event)

    def block_memo(self) -> None:
        """Mark the executing call as dependent on its consumer, so it is never replayed."""

        self.memo_blocked = True

    def add_dependency(self, identity: DeclarationIdentity) -> MacroExpansionFacts:
        """Record a resolved dependency in encounter order."""

        self.dependencies.append(identity)
        return self

    def add_usage(self, usage: UsageRecord) -> MacroExpansionFacts:
        """Record a resolved macro-to-macro edge in encounter order."""

        self.usages.append(usage)
        return self

    def record_call_site_refs(self, refs: tuple[SqlResourceRef, ...]) -> None:
        """Record references written as arguments of every macro call being expanded."""

        for ref in refs:
            self.note_event((ARGUMENT_REFERENCE_EVENT, ref.kind.value, ref.name))
        self.argument_references.update(dict.fromkeys(refs))
        for approved in self.call_site_refs:
            approved.update(refs)

    def open_call_site(self) -> MacroExpansionFacts:
        """Start collecting the references written as one macro call's arguments."""

        self.call_site_refs.append(set())
        return self

    def close_call_site(self) -> frozenset[SqlResourceRef]:
        """Stop collecting for the innermost macro call and return its argument references."""

        return frozenset(self.call_site_refs.pop())

    def begin_rendering(self, approved: frozenset[SqlResourceRef]) -> MacroExpansionFacts:
        """Approve the call-site argument references of the macro about to run."""

        self.rendering_approved.append(approved)
        return self

    def end_rendering(self) -> MacroExpansionFacts:
        """Restore the approvals of the enclosing macro after one macro returns."""

        self.rendering_approved.pop()
        return self

    def render_relation(self, ref: object) -> str:
        """Render a reference a macro formats; only call-site arguments become placeholders."""

        from sqlbuild.compiler.compile._helpers.explicit_references.macro_arguments import (
            reference_call_text,
            relation_placeholder_text,
        )

        if not isinstance(ref, SqlResourceRef):
            raise CompileInputError("Only typed resource references render as relations")
        if not self.rendering_approved or ref not in self.rendering_approved[-1]:
            return reference_call_text(ref)
        return relation_placeholder_text(self.relations.setdefault(ref, len(self.relations)))

    def render_relation_placeholders(self, sql: str) -> str:
        """Replace typed reference placeholders with the reference call written at the call site."""

        from sqlbuild.compiler.compile._helpers.explicit_references.macro_arguments import (
            render_relation_placeholders,
        )

        return render_relation_placeholders(sql=sql, relations=self.relations)
