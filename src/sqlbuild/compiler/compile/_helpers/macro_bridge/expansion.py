"""Expand one authored string through the native macro bridge, executing misses in Python."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.render.macros import (
    _evaluate_macro_call,
    _expansion_declarations,
    _record_macro_declaration_usage,
    _record_macro_use,
    _report_generated_references,
)
from sqlbuild.compiler.compile.classes.macro_expansion_facts import MacroExpansionFacts
from sqlbuild.compiler.compile.constants import MACRO_TOKEN
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
    ExpansionSpan,
    MacroExpansionState,
)
from sqlbuild.compiler.frontier.exceptions import NativeStageMismatchError
from sqlbuild.compiler.frontier.main.report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite
from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.constants import (
    ARGUMENT_REFERENCE_EVENT,
    DECLARATION_READ_EVENT,
    GENERATED_SQL_EVENT,
    MACRO_USE_EVENT,
)
from sqlbuild.compiler.macro_bridge.models import (
    MacroCallClass,
    MacroCallScan,
    MacroCallSite,
    MacroScanFailure,
)
from sqlbuild.compiler.macro_bridge.types import MacroCallEvent, MacroCallRecord
from sqlbuild.compiler.scopes.models import DeclarationIdentity
from sqlbuild.compiler.scopes.types import DeclarationKind
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind


def expand_bridged_sql_macros(
    *,
    sql: str,
    consumer_path: Path,
    state: MacroExpansionState,
    bridge: MacroBridge,
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    """Expand one string, replaying memoized calls and running the rest in Python in order.

    Where a call's macro tree does not resolve, or the scan raises, no call of the string touches
    the memo: each is evaluated in order, so errors and side effects keep the plain expansion's
    order.
    """

    if MACRO_TOKEN not in sql:
        return sql, ()
    declarations: DeclarationResolutionContext | None = _expansion_declarations(
        state=state, consumer_path=consumer_path
    )
    scan: MacroCallScan = bridge.scan(sql)
    sites: tuple[MacroCallSite, ...] = scan.sites
    call_classes: list[MacroCallClass | None] = (
        []
        if scan.failure is not None
        else [
            bridge.call_class(
                site=site,
                declarations=declarations,
                loaded_macros=state.loaded_macros,
                macro_context=state.macro_context,
            )
            for site in sites
        ]
    )
    if scan.failure is not None or None in call_classes:
        unmemoised: list[str] = [
            _evaluated_call_output(
                sql=sql,
                consumer_path=consumer_path,
                state=state,
                declarations=declarations,
                site=site,
            )
            for site in sites
        ]
        if scan.failure is not None:
            _raise_scan_failure(
                sql=sql,
                consumer_path=consumer_path,
                state=state,
                declarations=declarations,
                failure=scan.failure,
            )
        return bridge.splice(sql=sql, sites=sites, outputs=unmemoised)
    outputs: list[str] = [
        _bridged_call_output(
            sql=sql,
            consumer_path=consumer_path,
            state=state,
            declarations=declarations,
            bridge=bridge,
            site=site,
            call_class=call_class,
        )
        for site, call_class in zip(sites, call_classes, strict=True)
        if call_class is not None
    ]
    return bridge.splice(sql=sql, sites=sites, outputs=outputs)


def _bridged_call_output(  # noqa: PLR0913
    *,
    sql: str,
    consumer_path: Path,
    state: MacroExpansionState,
    declarations: DeclarationResolutionContext | None,
    bridge: MacroBridge,
    site: MacroCallSite,
    call_class: MacroCallClass,
) -> str:
    facts: MacroExpansionFacts = state.facts
    if state.macro_overrides.keys() & set(site.tree_names or ()):
        return _mocked_call_output(sql=sql, consumer_path=consumer_path, state=state, site=site)
    call_text: str = sql[site.start : site.end]
    prior_relations: tuple[SqlResourceRef, ...] | None = (
        tuple(facts.relations) if site.typed_reference_text else None
    )
    class_id: int
    recorded: MacroCallRecord | None
    class_id, recorded = bridge.lookup(
        call_class=call_class, call_text=call_text, prior_relations=prior_relations
    )
    if recorded is not None:
        recorded_sql, relations, events = recorded
        for event in events:
            _replay_macro_call_event(
                event=event,
                consumer_path=consumer_path,
                state=state,
                declarations=declarations,
            )
        for relation in relations:
            _ = facts.relations.setdefault(relation, len(facts.relations))
        return facts.render_relation_placeholders(recorded_sql)
    known_relations: int = len(facts.relations)
    _ = facts.begin_event_log()
    try:
        macro_result: object
        next_index: int
        macro_result, next_index = _evaluate_macro_call(
            sql=sql,
            call_start_index=site.start,
            file_path=consumer_path,
            state=state,
            declarations=declarations,
            stack=(),
            top_level=True,
        )
    finally:
        events, replayable = facts.end_event_log()
    if not isinstance(macro_result, str):
        raise CompileInputError(
            f"Macro '@{site.name}' in '{consumer_path}' must return a SQL string when used "
            "directly in SQL"
        )
    if next_index != site.end:
        raise NativeStageMismatchError(
            f"Native macro call scan of '{consumer_path}' ended at {site.end}, Python at "
            f"{next_index}"
        )
    added_relations: tuple[SqlResourceRef, ...] = tuple(facts.relations)[known_relations:]
    if replayable and (prior_relations is not None or not added_relations):
        bridge.record(
            class_id=class_id,
            call_text=call_text,
            sql=macro_result,
            relations=added_relations,
            events=events,
        )
    return facts.render_relation_placeholders(macro_result)


def _raise_scan_failure(
    *,
    sql: str,
    consumer_path: Path,
    state: MacroExpansionState,
    declarations: DeclarationResolutionContext | None,
    failure: MacroScanFailure,
) -> None:
    """Raise where Python's scan raises: from the failing call's evaluation, or between calls."""

    if failure.call_start is None:
        raise CompileInputError(failure.message)
    _ = _evaluate_macro_call(
        sql=sql,
        call_start_index=failure.call_start,
        file_path=consumer_path,
        state=state,
        declarations=declarations,
        stack=(),
        top_level=True,
    )
    raise NativeStageMismatchError(
        f"Native macro call scan of '{consumer_path}' found no complete call at "
        f"{failure.call_start}; Python evaluated one"
    )


def _mocked_call_output(
    *, sql: str, consumer_path: Path, state: MacroExpansionState, site: MacroCallSite
) -> str:
    """Run a call whose tree a test mocks; its output differs from the shared memo's, so skip it."""

    report_native_fallback(site=NativeFallbackSite.MACRO_CALL_MOCKED, kind="test_mock")
    return _evaluated_call_output(
        sql=sql,
        consumer_path=consumer_path,
        state=state,
        declarations=_expansion_declarations(state=state, consumer_path=consumer_path),
        site=site,
    )


def _evaluated_call_output(
    *,
    sql: str,
    consumer_path: Path,
    state: MacroExpansionState,
    declarations: DeclarationResolutionContext | None,
    site: MacroCallSite,
) -> str:
    """Evaluate one natively scanned call in Python without the memo."""

    macro_result: object
    next_index: int
    macro_result, next_index = _evaluate_macro_call(
        sql=sql,
        call_start_index=site.start,
        file_path=consumer_path,
        state=state,
        declarations=declarations,
        stack=(),
        top_level=True,
    )
    if not isinstance(macro_result, str):
        raise CompileInputError(
            f"Macro '@{site.name}' in '{consumer_path}' must return a SQL string when used "
            "directly in SQL"
        )
    if next_index != site.end:
        raise NativeStageMismatchError(
            f"Native macro call scan of '{consumer_path}' ended at {site.end}, Python at "
            f"{next_index}"
        )
    return state.facts.render_relation_placeholders(macro_result)


def _replay_macro_call_event(
    *,
    event: MacroCallEvent,
    consumer_path: Path,
    state: MacroExpansionState,
    declarations: DeclarationResolutionContext | None,
) -> None:
    tag, first, second = event
    if tag == MACRO_USE_EVENT:
        _record_macro_use(
            macro_name=first,
            identity=(
                declarations.macro_records[first].identity
                if declarations is not None
                else DeclarationIdentity(kind=DeclarationKind.MACRO, name=first)
            ),
            state=state,
            declarations=declarations,
            stack=(),
        )
    elif tag == DECLARATION_READ_EVENT:
        if declarations is None:
            raise NativeStageMismatchError("Replayed a declaration read without declarations")
        _record_macro_declaration_usage(
            name=second, kind=DeclarationKind(first), declarations=declarations, state=state
        )
    elif tag == GENERATED_SQL_EVENT:
        _report_generated_references(
            macro_name=first,
            loaded_macro=(
                declarations.macros[first]
                if declarations is not None
                else state.loaded_macros[first]
            ),
            macro_result=second,
            file_path=consumer_path,
            state=state,
        )
    elif tag == ARGUMENT_REFERENCE_EVENT:
        state.facts.record_call_site_refs(
            (SqlResourceRef(kind=SqlResourceRefKind(first), name=second),)
        )
    else:
        raise NativeStageMismatchError(f"Unknown macro call event {tag}")
