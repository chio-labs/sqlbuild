"""Successful top-level macro calls shared by consumers that see identical declarations."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile._helpers.refs.references import contains_sql_reference_call
from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads
from sqlbuild.compiler.compile.models import CompilerDiagnostic, MemoizedMacroCall


class MacroCallMemo:
    """Replay deterministic macro calls by macro name and authored argument text."""

    def __init__(self) -> None:
        self._calls: dict[str, dict[str, MemoizedMacroCall]] = {}

    def calls_for(self, macro_name: str) -> dict[str, MemoizedMacroCall] | None:
        """Return remembered calls of one macro keyed by argument text, if any."""

        return self._calls.get(macro_name)

    def remember(
        self,
        *,
        macro_name: str,
        arguments: str,
        call: MemoizedMacroCall,
        observed: tuple[CompileInputReads, list[tuple[tuple[str, ...], CompilerDiagnostic]]]
        | None = None,
    ) -> None:
        """Keep a diagnostic-free call, with its input reads, to replay for another consumer."""

        if contains_sql_reference_call(call.sql):
            return
        if any(usage.consumer != call.consumer for usage in call.usages):
            return
        if observed is not None:
            reads, reported = observed
            if reported:
                return
            call = replace(
                call,
                environment_names=reads.environment_names,
                settings_classes=reads.settings_classes,
                read_run_id=reads.read_run_id,
            )
        _ = self._calls.setdefault(macro_name, {}).setdefault(arguments, call)
