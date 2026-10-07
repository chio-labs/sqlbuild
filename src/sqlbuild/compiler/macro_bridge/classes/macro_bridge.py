"""Per-compile state of the native macro bridge: call-site scans, call classes and the memo."""

from __future__ import annotations

import logging
import sys
from collections.abc import Hashable, Mapping
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
    ExpansionSpan,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.macro_bridge._helpers.store_environment import (
    digest_module_files,
    module_digests_metadata,
    module_sources,
    project_fingerprint,
    store_environment,
    unchanged_module_digests,
)
from sqlbuild.compiler.macro_bridge._helpers.store_keys import (
    call_class_store_text,
    context_store_token,
    macro_store_token,
)
from sqlbuild.compiler.macro_bridge.constants import MACRO_CALL_STORE_FILE_NAME
from sqlbuild.compiler.macro_bridge.models import MacroCallClass, MacroCallSite, ModuleSources
from sqlbuild.compiler.macro_bridge.types import MacroCallEvent, MacroCallRecord
from sqlbuild.compiler.scopes.models import DeclarationIdentity
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
        self._name_tokens: dict[tuple[int, str], tuple[Hashable, str | None] | None] = {}
        self._context_tokens: dict[tuple[int, int], tuple[Hashable, str | None]] = {}
        self._store_path: Path | None = None
        self._store_trusted: bool = False
        self._module_digests: dict[str, str] = {}
        self._observed_modules: dict[str, object] = {}
        self._project_inputs: tuple[Path, list[str], str] = (Path(), [], "")

    def attach_store(self, *, cache_dir: Path, project_dir: Path, model_paths: list[str]) -> None:
        """Reuse call results stored by earlier compiles of the same code and project files."""

        if self._store_path is not None:
            return
        path: Path = cache_dir / MACRO_CALL_STORE_FILE_NAME
        metadata: bytes
        loaded: int
        try:
            if not self._observe_modules():
                logging.getLogger(__name__).debug("Macro call store not used: unknown module code")
                return
            fingerprint: str = project_fingerprint(project_dir=project_dir, model_paths=model_paths)
            environment: str = store_environment(project_dir=project_dir, fingerprint=fingerprint)
            metadata, loaded = self._memo.attach_store(str(path), environment)
        except (OSError, RuntimeError) as error:
            logging.getLogger(__name__).debug("Macro call store not loaded: %s", error)
            return
        carried: dict[str, str] | None = (
            unchanged_module_digests(metadata=metadata, known=self._module_digests)
            if loaded
            else {}
        )
        if carried is None:
            self._memo.discard_store()
            carried = {}
        self._store_path = path
        self._store_trusted = True
        self._module_digests = {**carried, **self._module_digests}
        self._project_inputs = (project_dir, model_paths, fingerprint)
        self._name_tokens.clear()
        self._context_tokens.clear()

    def save_store(self) -> None:
        """Save the results this compile used or recorded, unless code or files it read changed."""

        if self._store_path is None or not self._store_trusted:
            return
        project_dir, model_paths, fingerprint = self._project_inputs
        try:
            if (
                not self._observe_modules()
                or digest_module_files(self._module_digests) != self._module_digests
                or project_fingerprint(project_dir=project_dir, model_paths=model_paths)
                != fingerprint
            ):
                logging.getLogger(__name__).debug(
                    "Macro call store not saved: code or files changed"
                )
                return
            _ = self._memo.save_store(
                str(self._store_path), module_digests_metadata(self._module_digests)
            )
        except (OSError, RuntimeError) as error:
            logging.getLogger(__name__).debug("Macro call store not saved: %s", error)

    def _observe_modules(self) -> bool:
        """Digest the files of modules loaded since the last look; False when one is unknown."""

        loaded: dict[str, object] = dict(sys.modules)
        added: list[object] = [
            module
            for name, module in loaded.items()
            if self._observed_modules.get(name) is not module
        ]
        self._observed_modules = loaded
        sources: ModuleSources = module_sources(added)
        digests: dict[str, str] | None = (
            digest_module_files(sources.paths) if sources.complete else None
        )
        if digests is None or any(
            self._module_digests.get(path, digest) != digest for path, digest in digests.items()
        ):
            self._store_trusted = False
            return False
        self._module_digests.update(digests)
        return True

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
    ) -> MacroCallClass | None:
        """Return what a call's result may depend on besides its text, or None if unresolvable."""

        owner: object = loaded_macros if declarations is None else declarations
        macros: Mapping[str, LoadedMacro] = (
            loaded_macros if declarations is None else declarations.macros
        )
        _ = self._retained.setdefault(id(owner), owner)
        _ = self._retained.setdefault(id(macro_context), macro_context)
        tokens: list[Hashable] = []
        store_tokens: list[str | None] = []
        for name in site.tree_names:
            token: tuple[Hashable, str | None] | None = self._name_token(
                owner=owner, macros=macros, declarations=declarations, name=name
            )
            if token is None:
                return None
            tokens.append(token[0])
            store_tokens.append(token[1])
        injects_context: bool = any(macros[name].injects_context for name in site.tree_names)
        context: tuple[Hashable, str | None] | None = (
            self._context_token(owner=owner, declarations=declarations, macro_context=macro_context)
            if injects_context
            else None
        )
        persistent_tokens: tuple[str, ...] = tuple(
            token for token in store_tokens if token is not None
        )
        return MacroCallClass(
            key=(tuple(tokens), None if context is None else context[0]),
            macro_store_tokens=persistent_tokens,
            context_store_token=None if context is None else context[1],
            persistent=len(persistent_tokens) == len(store_tokens)
            and (context is None or context[1] is not None),
        )

    def lookup(
        self,
        *,
        call_class: MacroCallClass,
        call_text: str,
        prior_relations: tuple[SqlResourceRef, ...] | None,
    ) -> tuple[int, MacroCallRecord | None]:
        """Return the class id of a call and its recorded or stored result, if any."""

        class_key: Hashable = (call_class.key, prior_relations)
        class_id: int | None = self._class_ids.get(class_key)
        if class_id is None:
            class_id = self._class_ids[class_key] = len(self._class_ids)
            if self._store_path is not None and call_class.persistent:
                self._memo.set_persistent_class(
                    class_id,
                    call_class_store_text(
                        macro_tokens=call_class.macro_store_tokens,
                        context_token=call_class.context_store_token,
                        prior_relations=prior_relations,
                    ),
                )
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

        if self._store_trusted and len(sys.modules) != len(self._observed_modules):
            _ = self._observe_modules()
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

    def store_stats(self) -> tuple[int, int]:
        """Calls found in the store and calls recorded into it."""

        return self._memo.store_stats()

    def _name_token(
        self,
        *,
        owner: object,
        macros: Mapping[str, LoadedMacro],
        declarations: DeclarationResolutionContext | None,
        name: str,
    ) -> tuple[Hashable, str | None] | None:
        key: tuple[int, str] = (id(owner), name)
        if key in self._name_tokens:
            return self._name_tokens[key]
        loaded: LoadedMacro | None = macros.get(name)
        token: tuple[Hashable, str | None] | None = None
        if loaded is not None and (
            declarations is None or name not in declarations.inaccessible_macros
        ):
            identity: DeclarationIdentity | None = (
                declarations.macro_records[name].identity if declarations is not None else None
            )
            token = (
                (name, id(loaded), identity),
                macro_store_token(loaded=loaded, identity=identity)
                if self._store_path is not None
                else None,
            )
        self._name_tokens[key] = token
        return token

    def _context_token(
        self,
        *,
        owner: object,
        declarations: DeclarationResolutionContext | None,
        macro_context: MacroContext,
    ) -> tuple[Hashable, str | None]:
        key: tuple[int, int] = (id(owner), id(macro_context))
        token: tuple[Hashable, str | None] | None = self._context_tokens.get(key)
        if token is None:
            token = (
                (
                    id(macro_context),
                    None
                    if declarations is None
                    else (
                        tuple((name, id(value)) for name, value in declarations.constants.items()),
                        tuple((name, id(value)) for name, value in declarations.enums.items()),
                    ),
                ),
                context_store_token(macro_context=macro_context, declarations=declarations)
                if self._store_path is not None
                else None,
            )
            self._context_tokens[key] = token
        return token
