from scripts.native_module_paths._helpers.crates import native_module_path_errors
from scripts.native_module_paths._helpers.scan import scan_native_source

SOURCE_LABEL: str = "lib.rs"


def native_source_errors(source: str) -> tuple[str, ...]:
    """Scan one synthetic Rust file and resolve what it imports."""
    return native_module_path_errors(scan=scan_native_source(source=source, label=SOURCE_LABEL))
