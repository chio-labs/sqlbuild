"""Per-compile state of the native macro bridge: call-site scans, call classes and the memo."""

from __future__ import annotations

from collections.abc import Hashable, Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
    ExpansionSpan,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.macro_bridge.models import MacroCallSite
from sqlbuild.compiler.macro_bridge.types import MacroCallEvent, MacroCallRecord
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind


class MacroBridge:
    """Scan, memoize and splice macro calls for one compile; Python still runs every macro."""

    def __init__(self, *, python_version: tuple[int, int], unicode_version: str) -> None:
        self._python_version: tuple[int, int] = python_version
        self._unicode_version: str = unicode_version
        self._memo: _native.MacroCallMemo = _native.MacroCallMemo()
        self._class_ids: dict[Hashable, int] = {}
        self._retained: dict[int, object] = {}
        self._name_tokens: dict[tuple[int, str], Hashable | None] = {}
        self._context_tokens: dict[tuple[int, int], Hashable] = {}

    def scan(self, sql: str) -> tuple[MacroCallSite, ...] | None:
        """Return the top-level call sites of `sql`, or None when Python must expand it."""

        rows: list[tuple[int, int, str, list[str], bool]] | None = _native.scan_macro_call_sites(
            sql, self._python_version, self._unicode_version
        )
        if rows is None:
            return None
        return tuple(
            MacroCallSite(
                start=start,
                end=end,
                name=name,
                tree_names=tuple(tree_names),
                typed_reference_text=typed_reference_text,
            )
            for start, end, name, tree_names, typed_reference_text in rows
        )

    def call_class(
        self,
        *,
        site: MacroCallSite,
        declarations: DeclarationResolutionContext | None,
        loaded_macros: dict[str, LoadedMacro],
        macro_context: MacroContext,
    ) -> Hashable | None:
        """Return what a call's result may depend on besides its text, or None if unresolvable."""

        owner: object = loaded_macros if declarations is None else declarations
        macros: Mapping[str, LoadedMacro] = (
            loaded_macros if declarations is None else declarations.macros
        )
        _ = self._retained.setdefault(id(owner), owner)
        _ = self._retained.setdefault(id(macro_context), macro_context)
        tokens: list[Hashable] = []
        for name in site.tree_names:
            token: Hashable | None = self._name_token(
                owner=owner, macros=macros, declarations=declarations, name=name
            )
            if token is None:
                return None
            tokens.append(token)
        injects_context: bool = any(macros[name].injects_context for name in site.tree_names)
        context: Hashable | None = (
            self._context_token(owner=owner, declarations=declarations, macro_context=macro_context)
            if injects_context
            else None
        )
        return (tuple(tokens), context)

    def lookup(
        self,
        *,
        call_class: Hashable,
        call_text: str,
        prior_relations: tuple[SqlResourceRef, ...] | None,
    ) -> tuple[int, MacroCallRecord | None]:
        """Return the class id of a call and its recorded result, if one was recorded."""

        class_key: Hashable = (call_class, prior_relations)
        class_id: int = self._class_ids.setdefault(class_key, len(self._class_ids))
        found: tuple[str, list[tuple[str, str]], list[tuple[int, str, str]]] | None = (
            self._memo.lookup(class_id, call_text)
        )
        if found is None:
            return class_id, None
        sql, relations, events = found
        return class_id, (
            sql,
            tuple(
                SqlResourceRef(kind=SqlResourceRefKind(kind), name=name) for kind, name in relations
            ),
            tuple(events),
        )

    def record(
        self,
        *,
        class_id: int,
        call_text: str,
        sql: str,
        relations: tuple[SqlResourceRef, ...],
        events: tuple[MacroCallEvent, ...],
    ) -> None:
        """Record the result of one executed call for later calls of the same class and text."""

        self._memo.record(
            class_id,
            call_text,
            (sql, [(relation.kind.value, relation.name) for relation in relations], list(events)),
        )

    def splice(
        self, *, sql: str, sites: tuple[MacroCallSite, ...], outputs: list[str]
    ) -> tuple[str, tuple[ExpansionSpan, ...]]:
        """Replace each call site with its output, returning the SQL and substitution spans."""

        rendered: str
        spans: list[tuple[int, int, int, int]]
        rendered, spans = _native.splice_macro_calls(
            sql, [(site.start, site.end) for site in sites], outputs
        )
        return rendered, tuple(
            ExpansionSpan(
                source_start=source_start,
                source_end=source_end,
                output_start=output_start,
                output_end=output_end,
            )
            for source_start, source_end, output_start, output_end in spans
        )

    def stats(self) -> tuple[int, int, int]:
        """Memo hits, misses and recorded results so far."""

        return self._memo.stats()

    def _name_token(
        self,
        *,
        owner: object,
        macros: Mapping[str, LoadedMacro],
        declarations: DeclarationResolutionContext | None,
        name: str,
    ) -> Hashable | None:
        key: tuple[int, str] = (id(owner), name)
        if key in self._name_tokens:
            return self._name_tokens[key]
        loaded: LoadedMacro | None = macros.get(name)
        token: Hashable | None = (
            None
            if loaded is None
            or (declarations is not None and name in declarations.inaccessible_macros)
            else (
                name,
                id(loaded),
                declarations.macro_records[name].identity if declarations is not None else None,
            )
        )
        self._name_tokens[key] = token
        return token

    def _context_token(
        self,
        *,
        owner: object,
        declarations: DeclarationResolutionContext | None,
        macro_context: MacroContext,
    ) -> Hashable:
        key: tuple[int, int] = (id(owner), id(macro_context))
        token: Hashable | None = self._context_tokens.get(key)
        if token is None:
            token = (
                id(macro_context),
                None
                if declarations is None
                else (
                    tuple((name, id(value)) for name, value in declarations.constants.items()),
                    tuple((name, id(value)) for name, value in declarations.enums.items()),
                ),
            )
            self._context_tokens[key] = token
        return token
