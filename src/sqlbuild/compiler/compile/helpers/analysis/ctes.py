"""Polyglot-assisted top-level CTE extraction helpers."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_BODY_SQL as _POLYGLOT_ANALYSIS_BODY_SQL,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_CTE_FACTS as _POLYGLOT_ANALYSIS_CTE_FACTS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_NAME as _POLYGLOT_ANALYSIS_NAME,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_PROJECTIONS as _POLYGLOT_ANALYSIS_PROJECTIONS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SHAPE as _POLYGLOT_ANALYSIS_SHAPE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SHAPE_SELECT as _POLYGLOT_ANALYSIS_SHAPE_SELECT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT as _POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_KIND as _POLYGLOT_ANALYSIS_TRANSFORM_KIND,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_UPSTREAM as _POLYGLOT_ANALYSIS_UPSTREAM,
)
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.diagnostics.helpers.logging import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.compile")
_CEREMONIAL_SELECT_PATTERN: re.Pattern[str] = re.compile(r"\bSELECT\s+1\s*;?\s*$", re.IGNORECASE)


def extract_top_level_ctes_with_sql_analysis(
    *, sql: str, file_label: str, context_label: str
) -> tuple[tuple[str, str], ...] | None:
    """Extract top-level CTE aliases and rendered bodies with Polyglot when available."""

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return None
    try:
        analysis: Any = polyglot_module.analyze_query(sql, {"dialect": "generic"})
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="top-level CTE compact extraction failed; falling back",
            sqlbuild_file=file_label,
            sqlbuild_error=str(error),
        )
        return None
    if not isinstance(analysis, dict):
        return None
    if _CEREMONIAL_SELECT_PATTERN.search(sql) is None:
        return None
    if not _is_ceremonial_select_analysis(analysis):
        return None
    cte_facts: Any = analysis.get(_POLYGLOT_ANALYSIS_CTE_FACTS)
    if not isinstance(cte_facts, list) or not cte_facts:
        return None

    ctes: list[tuple[str, str]] = []
    seen_cte_names: set[str] = set()
    cte_fact: Any
    for cte_fact in cte_facts:
        if not isinstance(cte_fact, dict):
            return None
        cte_name: str | None = _cte_fact_name(cte_fact)
        if cte_name is None:
            return None
        if cte_name in seen_cte_names:
            raise CompileInputError(
                f"{context_label} '{file_label}' defines duplicate CTE '{cte_name}'"
            )
        seen_cte_names.add(cte_name)
        body_sql: Any = cte_fact.get(_POLYGLOT_ANALYSIS_BODY_SQL)
        if not isinstance(body_sql, str) or not body_sql:
            return None
        ctes.append((cte_name, body_sql))
    return tuple(ctes)


def _is_ceremonial_select_analysis(analysis: dict[str, Any]) -> bool:
    if analysis.get(_POLYGLOT_ANALYSIS_SHAPE) != _POLYGLOT_ANALYSIS_SHAPE_SELECT:
        return False
    projections: Any = analysis.get(_POLYGLOT_ANALYSIS_PROJECTIONS)
    if not isinstance(projections, list) or len(projections) != 1:
        return False
    projection: Any = projections[0]
    if not isinstance(projection, dict):
        return False
    if projection.get(_POLYGLOT_ANALYSIS_NAME) is not None:
        return False
    if projection.get(_POLYGLOT_ANALYSIS_TRANSFORM_KIND) != _POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT:
        return False
    upstream: Any = projection.get(_POLYGLOT_ANALYSIS_UPSTREAM)
    return isinstance(upstream, list) and not upstream


def _cte_fact_name(cte_fact: dict[str, Any]) -> str | None:
    name: Any = cte_fact.get(_POLYGLOT_ANALYSIS_NAME)
    return str(name) if name is not None else None
