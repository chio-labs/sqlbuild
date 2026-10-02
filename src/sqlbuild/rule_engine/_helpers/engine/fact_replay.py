"""Recompute and digest the compiler facts a custom-rule evaluation recorded."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path, PurePath

import orjson

from sqlbuild.rule_engine.classes.sql_document import SqlDocument
from sqlbuild.rule_engine.constants import (
    FACT_AUDITS_ALL,
    FACT_AUDITS_FOR_MODEL,
    FACT_COLUMNS_DECLARED,
    FACT_COLUMNS_INFERRED,
    FACT_COLUMNS_NAMES,
    FACT_CONTRACTS_ENFORCED,
    FACT_CONTRACTS_GRAIN,
    FACT_DECLARATIONS_CONSTANTS,
    FACT_DECLARATIONS_ENUMS,
    FACT_DECLARATIONS_PUBLIC_CONSTANTS,
    FACT_DECLARATIONS_PUBLIC_ENUMS,
    FACT_GRAPH_DEPENDENCIES,
    FACT_GRAPH_DEPENDENTS,
    FACT_PROJECT_AUDITS,
    FACT_PROJECT_FUNCTIONS,
    FACT_PROJECT_MODELS,
    FACT_PROJECT_SEEDS,
    FACT_PROJECT_SOURCES,
    FACT_PROJECT_TESTS,
    FACT_SQL_FOR_MODEL,
    FACT_TESTS_ALL,
    FACT_TESTS_FOR_MODEL,
    FACT_TREE_CHILDREN,
    FACT_TREE_DESCENDANTS,
    FACT_TREE_GLOB,
    FACT_TREE_PATHS,
    FACT_TREE_READ_TEXT,
    FACT_TREE_RELATIVE_PARTS,
    FACT_TREE_RESOURCES_UNDER,
)
from sqlbuild.rule_engine.exceptions import FactDigestError
from sqlbuild.rule_engine.models import Model, RuleFactViews
from sqlbuild.rule_engine.types import FactKey

_TRACKED_TEXT_SUFFIXES: frozenset[str] = frozenset({".py", ".sql", ".toml", ".yaml", ".yml"})
_ORJSON_OPTIONS: int = orjson.OPT_SORT_KEYS | orjson.OPT_NON_STR_KEYS

_GLOBAL_FACTS: dict[str, Callable[[RuleFactViews], object]] = {
    FACT_PROJECT_MODELS: lambda views: views.project.models,
    FACT_PROJECT_SOURCES: lambda views: views.project.sources,
    FACT_PROJECT_SEEDS: lambda views: views.project.seeds,
    FACT_PROJECT_FUNCTIONS: lambda views: views.project.functions,
    FACT_PROJECT_TESTS: lambda views: views.project.tests,
    FACT_PROJECT_AUDITS: lambda views: views.project.audits,
    FACT_TREE_PATHS: lambda views: views.project.tree.paths(),
    FACT_TESTS_ALL: lambda views: views.tests.all(),
    FACT_AUDITS_ALL: lambda views: views.audits.all(),
    FACT_DECLARATIONS_PUBLIC_ENUMS: lambda views: views.declarations.public_enums,
    FACT_DECLARATIONS_PUBLIC_CONSTANTS: lambda views: views.declarations.public_constants,
    FACT_DECLARATIONS_ENUMS: lambda views: views.declarations.enums,
    FACT_DECLARATIONS_CONSTANTS: lambda views: views.declarations.constants,
}
_MODEL_PATH_FACTS: dict[str, Callable[[RuleFactViews, Model], object]] = {
    FACT_SQL_FOR_MODEL: lambda views, model: views.sql.for_model(model),
    FACT_GRAPH_DEPENDENCIES: lambda views, model: views.graph.dependencies(model),
    FACT_GRAPH_DEPENDENTS: lambda views, model: views.graph.dependents(model),
    FACT_COLUMNS_DECLARED: lambda views, model: views.columns.declared(model),
    FACT_COLUMNS_INFERRED: lambda views, model: views.columns.inferred(model),
    FACT_COLUMNS_NAMES: lambda views, model: views.columns.names(model),
    FACT_CONTRACTS_ENFORCED: lambda views, model: views.contracts.enforced(model),
    FACT_CONTRACTS_GRAIN: lambda views, model: views.contracts.grain(model),
}
_MODEL_NAME_FACTS: dict[str, Callable[[RuleFactViews, Model], object]] = {
    FACT_TESTS_FOR_MODEL: lambda views, model: views.tests.for_model(model),
    FACT_AUDITS_FOR_MODEL: lambda views, model: views.audits.for_model(model),
}
_TEXT_FACTS: dict[str, Callable[[RuleFactViews, tuple[str, ...]], object]] = {
    FACT_TREE_CHILDREN: lambda views, arguments: views.project.tree.children(*arguments),
    FACT_TREE_DESCENDANTS: lambda views, arguments: views.project.tree.descendants(*arguments),
    FACT_TREE_GLOB: lambda views, arguments: views.project.tree.glob(*arguments),
    FACT_TREE_RELATIVE_PARTS: lambda views, arguments: views.project.tree.relative_parts(
        path=arguments[0], under=arguments[1]
    ),
    FACT_TREE_RESOURCES_UNDER: lambda views, arguments: views.project.tree.resources_under(
        *arguments
    ),
    FACT_TREE_READ_TEXT: lambda views, arguments: views.project.tree.read_text(*arguments),
}
_TEXT_FACT_ARITY: dict[str, int] = {
    FACT_TREE_CHILDREN: 1,
    FACT_TREE_DESCENDANTS: 1,
    FACT_TREE_GLOB: 1,
    FACT_TREE_RELATIVE_PARTS: 2,
    FACT_TREE_RESOURCES_UNDER: 1,
    FACT_TREE_READ_TEXT: 1,
}
_TREE_FACTS: frozenset[str] = frozenset({FACT_TREE_PATHS, *_TEXT_FACTS})


def fact_key_payload(key: tuple[object, ...]) -> list[str]:
    """Return the JSON form of one recorded fact key."""

    return [value.as_posix() if isinstance(value, PurePath) else str(value) for value in key]


def full_fact_keys(views: RuleFactViews) -> tuple[FactKey, ...]:
    """Return keys covering every fact a custom rule can observe through its context."""

    keys: list[FactKey] = [(fact,) for fact in _GLOBAL_FACTS]
    models: tuple[Model, ...] = views.project.models
    for model in models:
        path: str = model.path.as_posix()
        keys.extend((fact, path) for fact in _MODEL_PATH_FACTS)
        keys.extend((fact, model.name) for fact in _MODEL_NAME_FACTS)
    keys.extend(
        (FACT_TREE_READ_TEXT, node.value)
        for node in views.project.tree.paths()
        if node.is_file and Path(node.value).suffix.lower() in _TRACKED_TEXT_SUFFIXES
    )
    return tuple(keys)


def fact_outcome_digest(*, views: RuleFactViews, key: FactKey) -> str:
    """Recompute one recorded fact and digest its value or raised error."""

    try:
        value: object = _fact_value(views=views, key=key)
    except FactDigestError:
        raise
    except Exception as error:
        return fact_error_digest(error)
    return fact_value_digest(value)


def fact_value_digest(value: object) -> str:
    """Digest one fact value exactly as a recomputed fact would digest it."""

    return _encoded_digest(("value", value))


def fact_error_digest(error: Exception) -> str:
    """Digest one raised fact error exactly as a recomputed fact would digest it."""

    return _encoded_digest(("error", type(error).__name__, str(error)))


def is_tree_fact(key: FactKey) -> bool:
    """Return whether a fact is read from the live project filesystem."""

    return bool(key) and key[0] in _TREE_FACTS


def _fact_value(*, views: RuleFactViews, key: FactKey) -> object:
    if not key:
        raise FactDigestError("empty fact key")
    fact: str = key[0]
    arguments: tuple[str, ...] = key[1:]
    if fact in _GLOBAL_FACTS and not arguments:
        return _GLOBAL_FACTS[fact](views)
    if fact in _MODEL_PATH_FACTS and len(arguments) == 1:
        return _MODEL_PATH_FACTS[fact](
            views, Model(name="", path=Path(arguments[0]), materialization=None)
        )
    if fact in _MODEL_NAME_FACTS and len(arguments) == 1:
        return _MODEL_NAME_FACTS[fact](
            views, Model(name=arguments[0], path=Path(), materialization=None)
        )
    if fact in _TEXT_FACTS and len(arguments) == _TEXT_FACT_ARITY[fact]:
        return _TEXT_FACTS[fact](views, arguments)
    raise FactDigestError(f"unknown fact key: {fact}")


def _encoded_digest(value: object) -> str:
    try:
        encoded: bytes = orjson.dumps(value, default=_encode_default, option=_ORJSON_OPTIONS)
    except (TypeError, FactDigestError) as error:
        raise FactDigestError(str(error)) from error
    return hashlib.sha256(encoded).hexdigest()


def _encode_default(value: object) -> object:
    if isinstance(value, PurePath):
        return value.as_posix()
    if isinstance(value, SqlDocument):
        return {"source": value.source}
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(
            orjson.dumps(item, default=_encode_default, option=_ORJSON_OPTIONS).decode()
            for item in value
        )
    if isinstance(value, tuple):
        return list(value)
    raise FactDigestError(f"fact value of type {type(value).__name__} is not reproducible")
