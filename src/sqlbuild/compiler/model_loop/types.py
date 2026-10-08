"""Row shapes the native model loop exchanges with its Rust bindings."""

type NativeDeclarationReference = tuple[int, str, str | None, int, int]
type NativeDeclarationScan = tuple[tuple[NativeDeclarationReference, ...], int | None]
