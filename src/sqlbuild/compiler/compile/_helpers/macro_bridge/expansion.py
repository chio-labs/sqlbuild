"""Expand one authored string through the native macro bridge, executing misses in Python."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile._helpers.render.macros import (
    _expansion_declarations,
    _record_macro_declaration_usage,
    _record_macro_use,
    _report_generated_references,
    evaluate_macro_call,
    raise_failed_macro_call,
)
from sqlbuild.compiler.compile.classes.macro_expansion_facts import MacroExpansionFacts
from sqlbuild.compiler.compile.constants import MACRO_TOKEN
from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
    ExpansionSpan,
    MacroExpansionState,
)
from sqlbuild.compiler.frontier.exceptions import NativeStageMismatchError
from sqlbuild.compiler.frontier.main._report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite
from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from sqlbuild.compiler.macro_bridge.constants import (
    ARGUMENT_REFERENCE_EVENT,
    DECLARATION_READ_EVENT,
    GENERATED_SQL_EVENT,
    MACRO_USE_EVENT,
)
from sqlbuild.compiler.macro_bridge.main._scan_macro_calls import scan_macro_calls
from sqlbuild.compiler.macro_bridge.main._splice_macro_calls import splice_macro_calls
from sqlbuild.compiler.macro_bridge.models import (
    MacroCallClass,
    MacroCallScan,
    MacroCallSite,
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
    """Expand one string, replaying memoized calls; unresolved trees evaluate calls in order."""

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
        return _unmemoised_sql_macros(
            sql=sql, consumer_path=consumer_path, state=state, declarations=declarations, scan=scan
        )
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
        macro_result: str = _top_level_output(
            sql=sql,
            consumer_path=consumer_path,
            state=state,
            declarations=declarations,
            site=site,
        )
    finally:
        events, replayable = facts.end_event_log()
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


def expand_unbridged_sql_macros(
    *, sql: str, consumer_path: Path, state: MacroExpansionState
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    """Expand one string outside compile inputs: native call sites, each evaluated in order."""

    if MACRO_TOKEN not in sql:
        return sql, ()
    return _unmemoised_sql_macros(
        sql=sql,
        consumer_path=consumer_path,
        state=state,
        declarations=_expansion_declarations(state=state, consumer_path=consumer_path),
        scan=scan_macro_calls(sql=sql),
    )


def _unmemoised_sql_macros(
    *,
    sql: str,
    consumer_path: Path,
    state: MacroExpansionState,
    declarations: DeclarationResolutionContext | None,
    scan: MacroCallScan,
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    """Evaluate every call in order without the memo, raising where Python's scan raises."""

    outputs: list[str] = [
        _evaluated_call_output(
            sql=sql,
            consumer_path=consumer_path,
            state=state,
            declarations=declarations,
            site=site,
        )
        for site in scan.sites
    ]
    if scan.failure is not None:
        raise_failed_macro_call(
            failure=scan.failure,
            file_path=consumer_path,
            state=state,
            declarations=declarations,
        )
    return splice_macro_calls(sql=sql, sites=scan.sites, outputs=outputs)


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

    macro_result: str = _top_level_output(
        sql=sql,
        consumer_path=consumer_path,
        state=state,
        declarations=declarations,
        site=site,
    )
    return state.facts.render_relation_placeholders(macro_result)


def _top_level_output(
    *,
    sql: str,
    consumer_path: Path,
    state: MacroExpansionState,
    declarations: DeclarationResolutionContext | None,
    site: MacroCallSite,
) -> str:
    """One top-level call's SQL; a non-string result raises as Python's top-level check does."""

    macro_result: object = evaluate_macro_call(
        sql=sql,
        site=site,
        file_path=consumer_path,
        state=state,
        declarations=declarations,
        stack=(),
        top_level=True,
    )
    return cast(str, macro_result)


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
