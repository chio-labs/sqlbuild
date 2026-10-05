"""Volatile input reads of remembered macro calls, observed once and replayed per consumer."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.compiler.compile._helpers.diagnostics.collector import tapped_compile_diagnostics
from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.models import CompilerDiagnostic, MemoizedMacroCall
from sqlbuild.compiler.compile.types import CompileContextKey


@contextmanager
def observed_macro_call() -> Iterator[
    tuple[CompileInputReads, list[tuple[tuple[str, ...], CompilerDiagnostic]]]
]:
    """Observe the input reads and diagnostics of one macro call."""

    with (
        COMPILE_INPUT_READS.recording() as reads,
        tapped_compile_diagnostics() as reported,
    ):
        yield reads, reported


def replay_macro_call_reads(call: MemoizedMacroCall) -> None:
    """Report a remembered call's volatile input reads to the active compile recorders."""

    name: str
    for name in call.environment_names:
        COMPILE_INPUT_READS.environment_read(name)
    settings_class: type
    for settings_class in call.settings_classes:
        COMPILE_INPUT_READS.settings_class_read(settings_class)
    if call.read_run_id:
        COMPILE_INPUT_READS.context_read(CompileContextKey.RUN_ID)
