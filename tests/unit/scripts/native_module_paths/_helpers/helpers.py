import dataclasses
import importlib
import re
from enum import Enum
from pathlib import Path
from typing import Any

from scripts.native_module_paths._helpers.crates import native_module_path_errors
from scripts.native_module_paths._helpers.scan import scan_native_source

SOURCE_LABEL: str = "lib.rs"
FENSU_CONFIG: Path = Path(__file__).parents[5] / "fensu.toml"


def native_source_errors(source: str) -> tuple[str, ...]:
    """Scan one synthetic Rust file and resolve what it imports."""
    return native_module_path_errors(scan=scan_native_source(source=source, label=SOURCE_LABEL))


KIND_BY_TRAITS: dict[tuple[bool, bool, bool], str] = {
    (True, True, True): "exception",
    (True, False, True): "class",
    (False, False, True): "function",
    (False, False, False): "value",
}


def resolved_kind(value: object) -> str:
    """The host kind of a resolved entry: class, exception, function or value."""
    is_class: bool = isinstance(value, type)
    is_exception: bool = BaseException in getattr(value, "__mro__", ())
    return KIND_BY_TRAITS[(is_class, is_exception, callable(value))]


HOST_RESULT_MODELS: Path = Path(__file__).parents[5] / "crates/sqlbuild-host/src/models.rs"
MIRRORED_ITEM: str = r"/// [^\n]* Mirrors `([\w.]+)`[^\n]*\n#\[derive[^\n]*\]\npub {kind} (\w+)"
ENUM_VALUE: re.Pattern[str] = re.compile(r'=> "([^"]*)",')
STRUCT_FIELD: re.Pattern[str] = re.compile(r"\n    pub (\w+): ")


def mirrored_items(*, source: str, kind: str) -> dict[str, str]:
    """Each Python path the source mirrors with an item of `kind`, mapped to the Rust item name."""
    return dict(re.findall(MIRRORED_ITEM.format(kind=kind), source))


def rust_enum_values(*, source: str, name: str) -> tuple[str, ...]:
    """The Python values the `ResultEnum` implementation of `name` lists, in order."""
    body: str = source.split(f"impl ResultEnum for {name} {{", 1)[1].split("\n}", 1)[0]
    return tuple(ENUM_VALUE.findall(body))


def rust_struct_fields(*, source: str, name: str) -> tuple[str, ...]:
    """The field names of the Rust struct `name`, in order."""
    body: str = re.split(rf"pub struct {name}\b[^{{]*\{{", source, maxsplit=1)[1].split("\n}", 1)[0]
    return tuple(STRUCT_FIELD.findall("\n" + body))


def python_object(*, path: str) -> Any:
    """The Python object at a dotted `module.name` path."""
    module, _, name = path.rpartition(".")
    return getattr(importlib.import_module(module), name)


def python_enum_values(*, path: str) -> tuple[str, ...]:
    """The values of the Python string enum at `path`, in definition order."""
    members: type[Enum] = python_object(path=path)
    return tuple(str(member.value) for member in members)


def python_dataclass_fields(*, path: str) -> tuple[str, ...]:
    """The field names of the Python dataclass at `path`, in order."""
    return tuple(field.name for field in dataclasses.fields(python_object(path=path)))
