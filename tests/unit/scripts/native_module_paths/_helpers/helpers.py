from scripts.native_module_paths._helpers.crates import native_module_path_errors
from scripts.native_module_paths._helpers.scan import scan_native_source

SOURCE_LABEL: str = "lib.rs"


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
