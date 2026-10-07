//! Project layout names shared by native discovery, mirroring the Python discovery constants.

/// Root of SQL model files.
pub const MODELS_DIRECTORY: &str = "models";
/// Suffix of SQL files.
pub const SQL_FILE_SUFFIX: &str = ".sql";
/// The folder below a resource tree that holds grouped scoped declarations.
pub const DECLARATION_GROUP_DIRECTORY: &str = "_sqlbuild";
/// Inherited and local declaration directories whose files are never resources.
pub const SCOPED_DECLARATION_DIRECTORIES: [&str; 6] = [
    "macros",
    "enums",
    "constants",
    "_macros",
    "_enums",
    "_constants",
];
/// Resource trees that may hold scoped declarations, in Python's lookup order.
pub const CANONICAL_AUTHORED_ROOTS: [&[&str]; 5] = [
    &["models"],
    &["tests", "unit"],
    &["tests", "scenarios"],
    &["functions", "sql"],
    &["sources"],
];
/// The SQL test root, whose `macros/` SQL files are tests rather than declarations.
pub const SQL_TESTS_ROOT: &[&str] = &["tests", "unit"];
/// The directory of macro tests below the SQL test root.
pub const MACRO_TESTS_DIRECTORY: &str = "macros";
