"""Check every Python module path the native crates import by string."""

from __future__ import annotations

from pathlib import Path

from scripts.native_module_paths._helpers.resolve import unresolved_reference_error
from scripts.native_module_paths._helpers.scan import scan_native_source
from scripts.native_module_paths.constants import RUST_SOURCE_GLOB, SCANNED_SOURCE_ROOTS
from scripts.native_module_paths.models import ModulePathReference, NativeModulePathScan


def scan_native_crates(*, root: Path) -> NativeModulePathScan:
    """Scan every Rust file of the crates that call Python, in path order."""
    references: list[ModulePathReference] = []
    logger_names: set[str] = set()
    violations: list[str] = []
    for source_root in SCANNED_SOURCE_ROOTS:
        for path in sorted((root / source_root).rglob(RUST_SOURCE_GLOB)):
            scan: NativeModulePathScan = scan_native_source(
                source=path.read_text(encoding="utf-8"), label=path.relative_to(root).as_posix()
            )
            references.extend(scan.references)
            logger_names.update(scan.logger_names)
            violations.extend(scan.violations)
    return NativeModulePathScan(
        references=tuple(references),
        logger_names=tuple(sorted(logger_names)),
        violations=tuple(violations),
    )


def native_module_path_errors(*, scan: NativeModulePathScan) -> tuple[str, ...]:
    """Every policy violation, then every reference that does not resolve."""
    unresolved: list[str] = []
    for reference in scan.references:
        error: str | None = unresolved_reference_error(reference=reference)
        if error is not None:
            unresolved.append(error)
    return scan.violations + tuple(unresolved)
