"""Seeded MODEL header values and engine-parity outcomes for the native model config tests."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import cast

import pytest

import sqlbuild._native as _native
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.auditing.main._parse_audit_instances import parse_audit_instances
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileAdapterContext, CompileProjectInputs
from sqlbuild.compiler.discovery.main._model_schema_columns import parse_schema_columns
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredSqlModelFile
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
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
    "na\u00efve_check",
    "\u00dcniqueCheck",
    " \u2003unique\u00a0",
)
_COLUMN_NAMES: tuple[str, ...] = (
    "order_id",
    "Order_ID",
    "amount",
    "caf\u00e9",
    "CAF\u00c9",
    "Stra\u00dfe",
    "STRASSE",
    "\u03a3\u0391\u03a3",
    "\u03c3\u03b1\u03c2",
    "\u0130d",
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
    (
        "thresholds",
        (
            None,
            {"warn": {"above": 1}},
            {"warn": {"below": 5}, "error": {"below": 1}},
            {"warn": {"below": 5}, "error": {"below": 5.0}},
            {"error": {"above": 1.5}, "warn": {"above": 1}},
            {"warn": {"outside": (1, 5)}, "error": {"outside": (0, 6.5)}},
            {"warn": {"outside": (1, 5)}, "error": {"outside": (2, 6)}},
            {"warn": {"outside": (5, 1)}},
            {"warn": {"outside": [1, 2]}},
            {"warn": {"outside": (1, True)}},
            {"warn": {"above": 1}, "error": {"below": 2}},
            {"warn": {"above": True}},
            {"warn": {"above": "1"}},
            {"warn": {"above": 2**70}},
            {"warn": {"above": 1, "below": 2}},
            {"warn": {"sideways": 1}},
            {"warn": None, "error": None},
            {"warn": 1},
            {"bogus": 1, "other": 2},
            {},
            "x",
        ),
    ),
    ("minimum_samples", (0, 5, -1, True, None, 2**70)),
    ("evidence_limit", (0, 10, -3, None)),
    ("values", (["PLACED", "SHIPPED"], None, {"nested": [1, 2]})),
    ("minimum", (1, 2.5)),
)


NATIVE_MODEL_CONFIG_ENTRIES: tuple[str, ...] = (
    "parse_model_header_metadata",
    "expand_config_templates",
)
_NATIVE_ENTRIES: dict[str, Callable[..., object]] = {
    name: getattr(_native, name) for name in NATIVE_MODEL_CONFIG_ENTRIES
}
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


def generated_header_metadata(*, rng: random.Random, count: int) -> list[tuple[object, object]]:
    """Return seeded `(columns, audits)` header values mixing valid and invalid shapes."""

    return [(_columns(rng=rng), _audit_list(rng=rng)) for _ in range(count)]


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
    entry: Callable[..., object] = _NATIVE_ENTRIES[name]

    def counted(*args: object) -> object:
        calls[name] += 1
        return entry(*args)

    return counted


def header_metadata_parity(*, headers: list[tuple[object, object]]) -> HeaderMetadataParity:
    """Compare the native parse or rejection with the YAML schema parsers Python still owns."""

    model_files: list[DiscoveredSqlModelFile] = [
        _model_file(index=index, columns=columns, audits=audits)
        for index, (columns, audits) in enumerate(headers)
    ]
    native: list[NativeHeaderMetadata] = [
        parse_native_header_metadata(
            raw_columns=model_file.header_values.get("columns"),
            raw_audits=model_file.header_values.get("audits"),
            column_locations=model_file.header_column_locations,
            file_path=model_file.relative_path,
        )
        for model_file in model_files
    ]
    return HeaderMetadataParity(
        mismatches=mismatches(
            inputs=[model_file.header_values for model_file in model_files],
            expected=[
                _shape(_python_metadata(model_file=model_file)) for model_file in model_files
            ],
            actual=[_native_shape(metadata) for metadata in native],
        ),
        parsed=sum(_native_error(metadata) is None for metadata in native),
        rejected=sum(_native_error(metadata) is not None for metadata in native),
    )


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


def _native_shape(parsed: NativeHeaderMetadata) -> object:
    error: _native.NativeConfigError | None = _native_error(parsed)
    shapes: list[object] = [
        list(
            error_shape(
                native_config_error(
                    error=cast(_native.NativeConfigError, error), bridge_independent=True
                )
            )[:4]
        )
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
        ((), (rng.choice(("format", "zone")),)), weights=(19, 1)
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
