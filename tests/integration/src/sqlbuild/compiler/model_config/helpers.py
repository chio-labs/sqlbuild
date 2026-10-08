"""Seeded MODEL header values and engine-parity outcomes for the native model config tests."""

from __future__ import annotations

import os
import random
from collections.abc import Callable
from dataclasses import dataclass, fields
from itertools import compress
from pathlib import Path
from typing import cast

import pytest

import sqlbuild._native as _native
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.auditing.main._parse_audit_instances import parse_audit_instances
from sqlbuild.compiler.compile._helpers.render.context_templates import expand_config_templates
from sqlbuild.compiler.compile._helpers.render.templating import (
    contains_template_data,
    expand_template_data,
)
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS, MACRO_CALL_PATTERN
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileAdapterContext, CompileProjectInputs
from sqlbuild.compiler.discovery.main._model_schema_columns import parse_schema_columns
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlModelFile
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.model_config.constants import UNSUPPORTED_OUTCOME
from sqlbuild.compiler.model_config.main._native_config_contains_macro_call import (
    native_config_contains_macro_call,
)
from sqlbuild.compiler.model_config.main._native_config_contains_template import (
    native_config_contains_template,
)
from sqlbuild.compiler.model_config.main._native_config_error import native_config_error
from sqlbuild.compiler.model_config.main._parse_native_header_metadata import (
    parse_native_header_metadata,
)
from sqlbuild.compiler.model_config.models import NativeHeaderMetadata
from sqlbuild.spec.contracts.main.resolve_effective_collection_rendering import (
    resolve_effective_collection_rendering,
)
from sqlbuild.spec.contracts.models import SourceLocation
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

_TEXTS: tuple[object, ...] = (
    "INTEGER",
    "Order amount",
    "caf\u00e9 total",
    "",
    "   ",
    "\u00a0",
    "${target.schema}",
    "@cents(amount)",
    "@cents\u2003(amount)",
    "@cents\x1f(amount)",
    "mail@example.com",
    "\x1c",
    1,
    True,
    None,
    1.5,
    ("tuple",),
)
_AUDIT_NAMES: tuple[str, ...] = (
    "not_null",
    "unique",
    "accepted_values",
    "NotNull",
    "row_count_",
    "",
    "_private",
    "a",
)
_COLUMN_NAMES: tuple[str, ...] = (
    "order_id",
    "Order_ID",
    "amount",
    "caf\u00e9",
    "status",
    " ",
    "\u00a0",
    "id",
)
_COLUMN_KEYS: tuple[str, ...] = ("type", "nullable", "description", "audits", "migrate_from")
_AUDIT_OPTIONS: tuple[tuple[str, tuple[object, ...]], ...] = (
    ("name", ("custom_name", "Bad Name", "", None, 1)),
    ("description", ("Checks the rows", "", None)),
    ("severity", ("warn", "error", "fatal", None, 1)),
    ("run_scope", ("final", "", None)),
    ("always_run", (True, False, None, "yes")),
    ("thresholds", (None, {"warn": {"above": 1}})),
    ("minimum_samples", (0, 5, -1, True, None, 2**70)),
    ("evidence_limit", (0, 10, -3, None)),
    ("values", (["PLACED", "SHIPPED"], None, {"nested": [1, 2]})),
    ("minimum", (1, 2.5)),
)


NATIVE_MODEL_CONFIG_ENTRIES: tuple[str, ...] = (
    "parse_model_header_metadata",
    "expand_config_templates",
    "config_contains_template",
    "config_contains_macro_call",
)
MODEL_CONFIG_PROJECT: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "orders"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
        '[connections.local]\ndatabase = "orders.duckdb"\n\n'
        '[defaults]\nmaterialized = "table"\n\n'
        '[targets.dev]\nconnection = "local"\n'
        "schema = \"${coalesce(ENV:SQB_MISSING_SCHEMA, 'dev')}_${CTX:model.name}\"\n"
    ),
    "models/orders.sql": (
        'MODEL (\n  materialized table,\n  description "Orders.",\n'
        "  tags [\"${if(eq(CTX:run.target, 'dev'), 'development', 'release')}\"],\n"
        "  columns (\n"
        "    order_id (type INTEGER, nullable false, audits [not_null (severity error), unique]),\n"
        '    status (audits [accepted_values (values ["placed", "shipped"])]),\n'
        "  ),\n);\n\nSELECT 1 AS order_id, 'placed' AS status\n"
    ),
    "models/customers.sql": (
        "MODEL (\n  materialized view,\n  columns (customer_id (type INTEGER)),\n);\n\n"
        "SELECT 1 AS customer_id\n"
    ),
}


@dataclass(frozen=True)
class HeaderMetadataParity:
    """How the native header metadata parse compared with Python's over one corpus."""

    mismatches: list[tuple[object, object, object]]
    parsed: int
    rejected: int
    unsupported: int


@dataclass(frozen=True)
class ConfigTemplateParity:
    """How native template expansion compared with Python's over one corpus."""

    mismatches: list[tuple[object, object, object]]
    expanded: int
    rejected: int
    unsupported: int


@dataclass(frozen=True)
class TemplateFlags:
    """The resolver flags one expansion runs with."""

    allow_context: bool
    preserve_context_tokens: bool
    preserve_unknown_context: bool


@dataclass(frozen=True)
class ConfigPresenceParity:
    """How the native presence scans compared with Python's over one corpus."""

    mismatches: list[tuple[object, object, object]]
    present: int
    deferred: int


def generated_header_metadata(*, rng: random.Random, count: int) -> list[tuple[object, object]]:
    """Return seeded `(columns, audits)` header values mixing valid and invalid shapes."""

    return [(_columns(rng=rng), _audit_list(rng=rng)) for _ in range(count)]


def generated_config_values(*, rng: random.Random, count: int) -> list[object]:
    """Return seeded nested config values holding templates, macro calls and plain text."""

    return [_config_value(rng=rng, depth=0) for _ in range(count)]


def model_config_engine_outcome(
    *, project_dir: Path, engine: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, int], str]:
    """Build compile inputs under `engine`; count native entry calls and describe model config."""

    for relative_path, contents in MODEL_CONFIG_PROJECT.items():
        path: Path = project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    calls: dict[str, int] = dict.fromkeys(NATIVE_MODEL_CONFIG_ENTRIES, 0)
    for name in NATIVE_MODEL_CONFIG_ENTRIES:
        monkeypatch.setattr(_native, name, _counted(calls=calls, name=name))
    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, engine)
    adapter: DuckDbAdapter = DuckDbAdapter()
    inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs=discovered,
        adapter_context=CompileAdapterContext(
            value_renderer=adapter,
            collection_rendering=resolve_effective_collection_rendering(
                project_config=discovered.project_config, declaration_override=None
            ),
            python_functions_inherit_default_namespace=(
                adapter.python_functions_inherit_default_namespace()
            ),
            sql_lexical_syntax=adapter.sql_lexical_syntax,
        ),
        run_id="20261007T000000Z_orders",
        resolved_connection={},
        no_sql_validation=True,
        defer_model_sql_validation=True,
        no_cache=True,
    )
    return calls, repr(
        [(model.config, model.schema_entry, model.enum_columns) for model in inputs.model_inputs]
    )


def error_shape(error: Exception) -> tuple[object, ...]:
    """Return what a user sees of an error: its type, message, code and help."""

    return (
        type(error).__name__,
        str(error),
        getattr(error, "code", None),
        getattr(error, "help", None),
        getattr(error, "bridge_independent", None),
    )


def _counted(*, calls: dict[str, int], name: str) -> Callable[..., object]:
    entry: Callable[..., object] = getattr(_native, name)

    def counted(*args: object) -> object:
        calls[name] += 1
        return entry(*args)

    return counted


def generated_template_values(*, rng: random.Random, count: int) -> list[object]:
    """Return seeded config values holding valid, invalid and unusual `${...}` templates."""

    return [_template_value(rng=rng, depth=0) for _ in range(count)]


def config_template_parity(*, values: list[object], flags: TemplateFlags) -> ConfigTemplateParity:
    """Compare native expansion, its reads and its rejections with Python's expansion."""

    answered: list[object] = list(
        compress(
            values,
            [
                _native_classification(value=value, flags=flags) != UNSUPPORTED_OUTCOME
                for value in values
            ],
        )
    )
    outcomes: list[tuple[object, object, object]] = [
        (value, _python_expansion(value=value, flags=flags), _native_expansion(value, flags))
        for value in answered
    ]
    return ConfigTemplateParity(
        mismatches=mismatches(
            inputs=[value for value, _, _ in outcomes],
            expected=[expected for _, expected, _ in outcomes],
            actual=[actual for _, _, actual in outcomes],
        ),
        expanded=sum(not _is_error(actual) for _, _, actual in outcomes),
        rejected=sum(_is_error(actual) for _, _, actual in outcomes),
        unsupported=len(values) - len(outcomes),
    )


def _python_expansion(*, value: object, flags: TemplateFlags) -> object:
    with COMPILE_INPUT_READS.recording() as reads:
        try:
            result: object = expand_template_data(
                value=value,
                variables=TEMPLATE_VARIABLES,
                context_values=TEMPLATE_CONTEXT,
                context_label="model config",
                allow_context=flags.allow_context,
                preserve_context_tokens=flags.preserve_context_tokens,
                preserve_unknown_context=flags.preserve_unknown_context,
            )
        except CompileInputError as error:
            return _python_error_shape(error)
    return (_expansion_shape(result), reads.environment_names, reads.read_run_id)


def _python_error_shape(error: Exception) -> tuple[object, ...]:
    return (*error_shape(error)[:4], True)


def _is_error(outcome: object) -> bool:
    return isinstance(outcome, tuple) and len(outcome) == len(error_shape(ValueError()))


def _native_classification(*, value: object, flags: TemplateFlags) -> object:
    return _native.expand_config_templates(
        value,
        (TEMPLATE_VARIABLES, os.environ, TEMPLATE_CONTEXT),
        (
            flags.allow_context,
            flags.preserve_context_tokens,
            flags.preserve_unknown_context,
            "model config",
        ),
    )


def _native_expansion(value: object, flags: TemplateFlags) -> object:
    with COMPILE_INPUT_READS.recording() as reads:
        try:
            result: object = expand_config_templates(
                value=value,
                variables=TEMPLATE_VARIABLES,
                context_values=TEMPLATE_CONTEXT,
                context_label="model config",
                allow_context=flags.allow_context,
                preserve_context_tokens=flags.preserve_context_tokens,
                preserve_unknown_context=flags.preserve_unknown_context,
                native=True,
            )
        except CompileInputError as error:
            return error_shape(error)
    return (_expansion_shape(result), reads.environment_names, reads.read_run_id)


def _expansion_shape(value: object) -> object:
    return (repr(value), _type_tree(value))


def _type_tree(value: object) -> object:
    children: tuple[object, ...] = _CHILDREN.get(type(value), _no_children)(value)
    return (type(value).__name__, tuple(_type_tree(item) for item in children))


def _no_children(value: object) -> tuple[object, ...]:
    del value
    return ()


def _mapping_children(value: object) -> tuple[object, ...]:
    return tuple(cast(dict[object, object], value).values())


def _sequence_children(value: object) -> tuple[object, ...]:
    return tuple(cast(tuple[object, ...], value))


_CHILDREN: dict[type, Callable[[object], tuple[object, ...]]] = {
    dict: _mapping_children,
    list: _sequence_children,
    tuple: _sequence_children,
}


def header_metadata_parity(*, headers: list[tuple[object, object]]) -> HeaderMetadataParity:
    """Compare the native parse or rejection with Python's wherever native answers."""

    model_files: list[DiscoveredSqlModelFile] = [
        _model_file(index=index, columns=columns, audits=audits)
        for index, (columns, audits) in enumerate(headers)
    ]
    native: dict[Path, NativeHeaderMetadata] = parse_native_header_metadata(model_files=model_files)
    parsed: list[NativeHeaderMetadata | None] = [
        native.get(model_file.file_path) for model_file in model_files
    ]
    python: list[object] = [_python_metadata(model_file=model_file) for model_file in model_files]
    compared: list[tuple[DiscoveredSqlModelFile, object, NativeHeaderMetadata | None]] = list(
        compress(
            zip(model_files, python, parsed, strict=True),
            [metadata is not None for metadata in parsed],
        )
    )
    return HeaderMetadataParity(
        mismatches=mismatches(
            inputs=[model_file.header_values for model_file, _, _ in compared],
            expected=[_shape(value) for _, value, _ in compared],
            actual=[_native_shape(metadata) for _, _, metadata in compared],
        ),
        parsed=sum(_native_error(metadata) is None for metadata in native.values()),
        rejected=sum(_native_error(metadata) is not None for metadata in native.values()),
        unsupported=len(model_files) - len(compared),
    )


def config_presence_parity(*, values: list[object]) -> ConfigPresenceParity:
    """Compare the native template and macro scans with Python's wherever they answer."""

    native: list[tuple[bool | None, bool | None]] = [
        (native_config_contains_template(value), native_config_contains_macro_call(value))
        for value in values
    ]
    python: list[tuple[bool, bool]] = [
        (contains_template_data(value), _python_contains_macro(value)) for value in values
    ]
    answered: list[tuple[object, tuple[bool, bool], tuple[bool | None, bool | None]]] = list(
        compress(
            zip(values, python, native, strict=True),
            [None not in answer for answer in native],
        )
    )
    return ConfigPresenceParity(
        mismatches=mismatches(
            inputs=[value for value, _, _ in answered],
            expected=[expected for _, expected, _ in answered],
            actual=[actual for _, _, actual in answered],
        ),
        present=sum(any(expected) for _, expected, _ in answered),
        deferred=len(values) - len(answered),
    )


def _python_contains_macro(value: object) -> bool:
    return _MACRO_SCANS.get(type(value), _absent)(value)


def _absent(value: object) -> bool:
    del value
    return False


def _string_contains_macro(value: object) -> bool:
    return MACRO_CALL_PATTERN.search(str(value)) is not None


def _mapping_contains_macro(value: object) -> bool:
    return any(_python_contains_macro(item) for item in cast(dict[object, object], value).values())


def _sequence_contains_macro(value: object) -> bool:
    return any(_python_contains_macro(item) for item in cast(tuple[object, ...], value))


_MACRO_SCANS: dict[type, Callable[[object], bool]] = {
    str: _string_contains_macro,
    dict: _mapping_contains_macro,
    list: _sequence_contains_macro,
    tuple: _sequence_contains_macro,
}


def _python_metadata(*, model_file: DiscoveredSqlModelFile) -> object:
    try:
        return (
            parse_schema_columns(
                raw_columns=model_file.header_values.get("columns"),
                file_path=model_file.relative_path,
                label="model",
                error_class=CompileInputError,
                column_locations=model_file.header_column_locations or {},
                allow_migrate_from=True,
            ),
            parse_audit_instances(
                raw_audits=model_file.header_values.get("audits"),
                file_path=model_file.relative_path,
                label="model",
                error_class=CompileInputError,
                null_as_empty=True,
            ),
        )
    except Exception as error:  # noqa: BLE001 - the exact Python outcome, whatever it is
        return list(error_shape(error)[:4])


def _shape(value: object) -> object:
    return _SHAPES.get(type(value), _unchanged)(value)


def _unchanged(value: object) -> object:
    return value


def _metadata_shape(value: object) -> object:
    return (repr(value), _attribute_orders(value), _locations(value))


def _native_shape(metadata: NativeHeaderMetadata | None) -> object:
    parsed: NativeHeaderMetadata = cast(NativeHeaderMetadata, metadata)
    error: _native.NativeConfigError | None = _native_error(parsed)
    shapes: list[object] = [
        list(error_shape(native_config_error(error=cast(_native.NativeConfigError, error)))[:4])
        for _ in range(error is not None)
    ]
    return (*shapes, _shape((parsed.columns, parsed.audits)))[0]


def _native_error(metadata: NativeHeaderMetadata) -> _native.NativeConfigError | None:
    return metadata.columns_error or metadata.audits_error


_SHAPES: dict[type, Callable[[object], object]] = {tuple: _metadata_shape}


def _attribute_orders(value: object) -> object:
    return _item_orders(_flattened(value))


def _item_orders(items: tuple[object, ...]) -> object:
    return tuple(
        (type(item).__name__, tuple(vars(item)), _item_orders(getattr(item, "audits", ())))
        for item in items
    )


def _locations(value: object) -> object:
    return tuple(_item_locations(item) for item in _flattened(value))


def _item_locations(item: object) -> object:
    audit_locations: tuple[object, ...] = tuple(
        audit.location for audit in getattr(item, "audits", ())
    )
    return (getattr(item, "location", None), audit_locations)


def _flattened(value: object) -> tuple[object, ...]:
    columns, audits = cast(tuple[tuple[object, ...], tuple[object, ...]], value)
    return (*columns, *audits)


def _model_file(*, index: int, columns: object, audits: object) -> DiscoveredSqlModelFile:
    relative_path: Path = Path("models") / f"model_{index}.sql"
    names: list[str] = [*filter(_is_text, getattr(columns, "keys", tuple)())]
    locations: dict[str, SourceLocation] = {
        name: SourceLocation(path=relative_path, line=line + 2, column=3)
        for line, name in enumerate(names[: len(names) * (index % 2)])
    }
    model_file: DiscoveredSqlModelFile = object.__new__(DiscoveredSqlModelFile)
    values: dict[str, object] = {field.name: None for field in fields(DiscoveredSqlModelFile)}
    values.update(
        file_path=Path("/project") / relative_path,
        relative_path=relative_path,
        header_values={"columns": columns, "audits": audits},
        header_column_locations=locations,
    )
    for name, value in values.items():
        object.__setattr__(model_file, name, value)
    return model_file


def _is_text(value: object) -> bool:
    return isinstance(value, str)


def _columns(*, rng: random.Random) -> object:
    return rng.choices(
        (None, rng.choice(([], "columns", 1, ("order_id",))), _column_mapping(rng=rng)),
        weights=(8, 4, 88),
    )[0]


def _column_mapping(*, rng: random.Random) -> dict[object, object]:
    return {
        rng.choices((rng.choice(_COLUMN_NAMES), rng.choice((1, None))), weights=(9, 1))[0]: (
            _column(rng=rng)
        )
        for _ in range(rng.randint(0, 5))
    }


def _column(*, rng: random.Random) -> object:
    keys: list[str] = rng.sample(_COLUMN_KEYS, k=rng.randint(0, len(_COLUMN_KEYS)))
    column: dict[object, object] = {key: _COLUMN_VALUES[key](rng) for key in keys}
    extra_keys: tuple[object, ...] = rng.choices(
        ((), (rng.choice(("format", 1)),)), weights=(19, 1)
    )[0]
    column.update(dict.fromkeys(extra_keys, "x"))
    return rng.choices((column, rng.choice((None, "INTEGER", []))), weights=(19, 1))[0]


def _text(rng: random.Random) -> object:
    return rng.choice(_TEXTS)


def _nullable(rng: random.Random) -> object:
    return rng.choice((True, False, None, "yes"))


def _audits(rng: random.Random) -> object:
    return _audit_list(rng=rng)


_COLUMN_VALUES: dict[str, Callable[[random.Random], object]] = {
    "type": _text,
    "nullable": _nullable,
    "description": _text,
    "audits": _audits,
    "migrate_from": _text,
}


def _audit_list(*, rng: random.Random) -> object:
    return rng.choices(
        (
            None,
            rng.choice(("not_null", {"unique": None}, ("unique",))),
            [_audit(rng=rng) for _ in range(rng.randint(0, 3))],
        ),
        weights=(30, 4, 66),
    )[0]


def _audit(*, rng: random.Random) -> object:
    name: str = rng.choice(_AUDIT_NAMES)
    options: list[tuple[str, tuple[object, ...]]] = rng.sample(_AUDIT_OPTIONS, k=rng.randint(0, 4))
    return rng.choices(
        (
            name,
            {name: None},
            rng.choice(({name: None, "unique": None}, {1: None}, {name: "x"}, 3)),
            {name: {key: rng.choice(choices) for key, choices in options}},
        ),
        weights=(35, 10, 5, 50),
    )[0]


def _template_value(*, rng: random.Random, depth: int) -> object:
    factories: tuple[Callable[[], object], ...] = (
        lambda: _template_text(rng=rng),
        lambda: rng.choice(_TEXTS),
        lambda: [_template_value(rng=rng, depth=depth + 1) for _ in range(rng.randint(0, 3))],
        lambda: tuple(_template_value(rng=rng, depth=depth + 1) for _ in range(rng.randint(0, 2))),
        lambda: {
            rng.choice(("schema", "database", "${key}", 1)): _template_value(
                rng=rng, depth=depth + 1
            )
            for _ in range(rng.randint(0, 3))
        },
    )
    return rng.choices(factories, weights=(60 + 1000 * (depth > 1), 10, 10, 5, 15))[0]()


def _template_text(*, rng: random.Random) -> str:
    parts: list[str] = [
        rng.choices(
            (f"${{{_template_expression(rng=rng, depth=0)}}}", rng.choice(_TEMPLATE_NOISE)),
            weights=(4, 1),
        )[0]
        for _ in range(rng.randint(1, 3))
    ]
    text: str = "".join(parts)
    noise: str = rng.choices((rng.choice(_TEMPLATE_NOISE), ""), weights=(15, 85))[0]
    position: int = rng.randrange(len(text) + 1)
    return text[:position] + noise + text[position:]


def _template_expression(*, rng: random.Random, depth: int) -> str:
    factories: tuple[Callable[[], str], ...] = (
        lambda: rng.choice(_TEMPLATE_REFERENCES),
        lambda: rng.choice(_TEMPLATE_LITERALS),
        lambda: "{}({})".format(
            rng.choice(_TEMPLATE_FUNCTIONS),
            rng.choice((",", ", ", " ,\t", "\x1f,")).join(
                _template_expression(rng=rng, depth=depth + 1)
                for _ in range(rng.choice((0, 1, 2, 2, 3, 3, 4)))
            ),
        ),
    )
    return rng.choices(factories, weights=(5, 3, 4 - 3 * (depth > 2)))[0]()


TEMPLATE_VARIABLES: dict[str, object] = {
    "flag": True,
    "zero": 0,
    "count": 12,
    "big": 2**70,
    "env": "prod",
    "spaced": " FALSE ",
    "ratio": 1.5,
    "items": [1, "a"],
    "mapping": {"a": 1},
    "none": None,
    "unicode": "caf\u00e9",
}
TEMPLATE_CONTEXT: dict[str, str | None] = {
    "run.id": "20261007T000000Z_abc",
    "run.target": "prod",
    "model.name": "orders",
    "model.schema": None,
}
TEMPLATE_ENVIRONMENT: dict[str, str] = {
    "SQB_TEMPLATE_SCHEMA": "analytics",
    "SQB_TEMPLATE_EMPTY": "",
    "SQB_TEMPLATE_ZERO": "0",
}
_TEMPLATE_REFERENCES: tuple[str, ...] = (
    *TEMPLATE_VARIABLES,
    "missing",
    "ENV:SQB_TEMPLATE_SCHEMA",
    "ENV:SQB_TEMPLATE_EMPTY",
    "ENV:SQB_TEMPLATE_ZERO",
    "ENV:SQB_TEMPLATE_MISSING",
    "CTX:run.id",
    "CTX:run.target",
    "CTX:model.name",
    "CTX:model.schema",
    "CTX:model.alias",
    "OTHER:name",
    "true",
    "false",
    "null",
)
_TEMPLATE_LITERALS: tuple[str, ...] = (
    "'prod'",
    '"0"',
    "''",
    "' False '",
    "'a\\'b'",
    "'caf\u00e9'",
    "'unterminated",
    "'trailing\\",
)
_TEMPLATE_FUNCTIONS: tuple[str, ...] = ("if", "eq", "ne", "coalesce", "upper")
_TEMPLATE_NOISE: tuple[str, ...] = (
    "orders_",
    "${",
    "}",
    "{",
    "$",
    "${}",
    "(",
    ")",
    ",",
    "\u00a0",
    "\u2003",
    "\x1c",
    " ",
    "caf\u00e9",
)


def _config_value(*, rng: random.Random, depth: int) -> object:
    factories: tuple[Callable[[], object], ...] = (
        lambda: rng.choice(_TEXTS),
        lambda: [_config_value(rng=rng, depth=depth + 1) for _ in range(rng.randint(0, 3))],
        lambda: tuple(_config_value(rng=rng, depth=depth + 1) for _ in range(rng.randint(0, 3))),
        lambda: {
            rng.choice(("schema", "${key}", "tags", 1)): _config_value(rng=rng, depth=depth + 1)
            for _ in range(rng.randint(0, 3))
        },
    )
    return rng.choices(factories, weights=(50 + 1000 * (depth > 2), 20, 10, 20))[0]()
