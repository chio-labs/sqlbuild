"""Native rendering facts for one compile's models, with per-model Python fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlReference, NativeModelRenderFacts
from sqlbuild.compiler.compile.types import NativeReference
from sqlbuild.compiler.profiling.main._metric import record_compile_metric
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax

_NATIVE_RESULT_LENGTH: int = 2


class NativeModelRendering:
    """Scan every model's variable-substituted SQL in one parallel native call."""

    def __init__(self, *, sqls: dict[Path, str | None], syntax: SqlLexicalSyntax) -> None:
        self._syntax_json: str = json.dumps(syntax.native_request(), sort_keys=True)
        self._interned: dict[NativeReference, CompileSqlReference] = {}
        self._natively_rendered: int = 0
        self._rendered: int = 0
        raw_results: object = _native.render_model_sql_batch(list(sqls.values()), self._syntax_json)
        if not isinstance(raw_results, list) or len(raw_results) != len(sqls):
            raise CompileInputError("native model rendering returned an invalid batch")
        self._facts: dict[Path, NativeModelRenderFacts | None] = {
            path: self._render_facts(raw_result) if sql is not None else None
            for (path, sql), raw_result in zip(sqls.items(), raw_results, strict=True)
        }

    def declaration_starts(self, path: Path) -> tuple[int, ...] | None:
        """Return natively scanned declaration reference offsets for one model, if any."""

        facts: NativeModelRenderFacts | None = self._facts.get(path)
        return facts.declaration_starts if facts is not None else None

    def model_references(
        self, *, path: Path, expanded_query_sql: str, var_substituted_sql: str
    ) -> tuple[CompileSqlReference, ...] | None:
        """Return natively scanned references of one model's final SQL, or ``None`` for Python."""

        self._rendered += 1
        facts: NativeModelRenderFacts | None = self._facts.get(path)
        if (
            facts is not None
            and facts.references is not None
            and expanded_query_sql == var_substituted_sql
        ):
            self._natively_rendered += 1
            return facts.references
        return self._converted(
            _native.extract_model_sql_references(expanded_query_sql, self._syntax_json)
        )

    def record_counts(self) -> None:
        """Report how many fresh renders the native batch served and how many fell back."""

        record_compile_metric(metric="model_render_native", value=self._natively_rendered)
        record_compile_metric(
            metric="model_render_fallback", value=self._rendered - self._natively_rendered
        )

    def _render_facts(self, raw_result: object) -> NativeModelRenderFacts:
        if not (
            isinstance(raw_result, tuple)
            and len(raw_result) == _NATIVE_RESULT_LENGTH
            and (raw_result[0] is None or isinstance(raw_result[0], list))
            and (raw_result[1] is None or isinstance(raw_result[1], list))
        ):
            raise CompileInputError("native model rendering returned an invalid result")
        starts: list[int] | None = cast(list[int] | None, raw_result[0])
        return NativeModelRenderFacts(
            declaration_starts=tuple(starts) if starts is not None else None,
            references=self._converted(cast(list[NativeReference] | None, raw_result[1])),
        )

    def _converted(
        self, raw_references: list[NativeReference] | None
    ) -> tuple[CompileSqlReference, ...] | None:
        if raw_references is None:
            return None
        return tuple(self._interned_reference(reference) for reference in raw_references)

    def _interned_reference(self, reference: NativeReference) -> CompileSqlReference:
        existing: CompileSqlReference | None = self._interned.get(reference)
        if existing is not None:
            return existing
        kind, name, package, call_argument_count = reference
        created: CompileSqlReference = CompileSqlReference(
            ref_kind=SqlReferenceKind(kind),
            ref_name=name,
            ref_package=package,
            call_argument_count=call_argument_count,
        )
        self._interned[reference] = created
        return created
