"""Find the Python module paths native Rust source imports by string."""

from __future__ import annotations

from scripts.native_module_paths.constants import (
    DOTTED_PATH,
    DYNAMIC_MODULE_PATHS,
    HOST_ENTRY,
    HOST_MODULE,
    IMPORT_GETATTR_CHAIN,
    IMPORT_HELPER_CALL,
    LITERAL_MODULE_ATTRIBUTE_PAIR,
    LOGGER_CONSTANT_NAME,
    PACKAGE_LITERAL,
    STRING_CONSTANT,
)
from scripts.native_module_paths.models import ModulePathReference, NativeModulePathScan


def scan_native_source(*, source: str, label: str) -> NativeModulePathScan:
    """Return the module paths, attributes, host entries and dynamic module paths in one file."""
    constants: dict[str, str] = {
        match.group(1): match.group(2) for match in STRING_CONSTANT.finditer(source)
    }
    logger_names: frozenset[str] = frozenset(
        value for name, value in constants.items() if LOGGER_CONSTANT_NAME.search(name)
    )
    references: list[ModulePathReference] = []
    violations: list[str] = []
    for match in PACKAGE_LITERAL.finditer(source):
        path: str = match.group(1)
        location: str = _location(source=source, label=label, offset=match.start())
        if DOTTED_PATH.fullmatch(path) is None:
            violations.append(f"{location}: '{path}' is not a complete dotted module path.")
        elif path not in logger_names:
            references.append(ModulePathReference(location=location, path=path))
    for pattern in (IMPORT_HELPER_CALL, IMPORT_GETATTR_CHAIN):
        for match in pattern.finditer(source):
            module: str | None = _module_argument(argument=match.group(1), constants=constants)
            if module is not None and module not in logger_names:
                references.append(
                    ModulePathReference(
                        location=_location(source=source, label=label, offset=match.start()),
                        path=module,
                        attribute=match.group(2),
                    )
                )
    for match in LITERAL_MODULE_ATTRIBUTE_PAIR.finditer(source):
        references.append(
            ModulePathReference(
                location=_location(source=source, label=label, offset=match.start()),
                path=match.group(1),
                attribute=match.group(2),
            )
        )
    references.extend(
        ModulePathReference(
            location=_location(source=source, label=label, offset=match.start()),
            path=HOST_MODULE,
            attribute=match.group(1),
        )
        for match in HOST_ENTRY.finditer(source)
    )
    for pattern in DYNAMIC_MODULE_PATHS:
        violations.extend(
            f"{_location(source=source, label=label, offset=match.start())}: module path is "
            "built at runtime; use a complete literal module path."
            for match in pattern.finditer(source)
        )
    return NativeModulePathScan(
        references=tuple(references),
        logger_names=tuple(sorted(logger_names)),
        violations=tuple(violations),
    )


def _module_argument(*, argument: str, constants: dict[str, str]) -> str | None:
    """The module a helper argument names: a literal, or a same-file package constant."""
    if argument.startswith('"'):
        return argument.strip('"')
    return constants.get(argument)


def _location(*, source: str, label: str, offset: int) -> str:
    line: int = source.count("\n", 0, offset) + 1
    return f"{label}:{line}"
