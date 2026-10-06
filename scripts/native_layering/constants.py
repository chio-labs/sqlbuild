"""Stable native layering policy constants."""

LAYERS_METADATA_KEY: str = "native-layers"
PYO3_PACKAGE: str = "pyo3"
POLYGLOT_PACKAGE: str = "polyglot-sql"
DEPENDENCY_TABLES: tuple[str, ...] = ("dependencies", "build-dependencies", "dev-dependencies")
CARGO_MANIFEST: str = "Cargo.toml"
PYPROJECT_MANIFEST: str = "pyproject.toml"
RELEASE_MANIFEST: str = ".release-please-manifest.json"
RELEASE_MANIFEST_PACKAGE: str = "."
