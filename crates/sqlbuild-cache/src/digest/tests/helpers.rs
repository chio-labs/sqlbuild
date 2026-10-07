use std::collections::HashSet;
use std::path::Path;

/// The model file the fingerprint test project leaves to the cache key.
pub(crate) const EXCLUDED_MODEL: &str = "models/orders.sql";

/// Write a small project: config, a macro, a model and files in skipped folders.
pub(crate) fn write_project(root: &Path) {
    for (relative_path, contents) in [
        ("sqlbuild_project.toml", "name = \"orders\"\n"),
        ("macros/cents.py", "def cents(amount):\n    return amount\n"),
        (EXCLUDED_MODEL, "SELECT 1 AS id\n"),
        ("target/cache/store.bin", "old"),
        ("macros/__pycache__/cents.pyc", "bytecode"),
        ("warehouse.duckdb", "pages"),
    ] {
        write_file(root, relative_path, contents);
    }
}

pub(crate) fn write_file(root: &Path, relative_path: &str, contents: &str) {
    let path = root.join(relative_path);
    std::fs::create_dir_all(path.parent().expect("parent")).expect("parent folder");
    std::fs::write(path, contents).expect("project file");
}

pub(crate) fn excluded_files() -> HashSet<String> {
    HashSet::from([EXCLUDED_MODEL.to_owned()])
}
