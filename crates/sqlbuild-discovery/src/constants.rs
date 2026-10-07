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
/// The SQL scenario root.
pub const SQL_SCENARIOS_ROOT: &str = "tests/scenarios";
/// The directory of macro tests below the SQL test root.
pub const MACRO_TESTS_DIRECTORY: &str = "macros";
/// Inherited declaration directories, which may also be project-wide global roots.
pub const GLOBAL_DECLARATION_DIRECTORIES: [&str; 3] = ["macros", "enums", "constants"];
/// Folder-local declaration directories.
pub const LOCAL_DECLARATION_DIRECTORIES: [&str; 3] = ["_macros", "_enums", "_constants"];
/// Directories a declaration group may hold for named declarations.
pub const GROUPED_NAMED_DECLARATION_DIRECTORIES: [&str; 6] = [
    "audits", "_audits", "schemas", "_schemas", "hooks", "_hooks",
];
/// Project-wide named declaration roles.
pub const GLOBAL_NAMED_DECLARATION_DIRECTORIES: [&str; 3] = ["audits", "schemas", "hooks"];
/// Suffix of macro files.
pub const PYTHON_FILE_SUFFIX: &str = ".py";
/// The stem of package initialisers, which are not macro files.
pub const PYTHON_INIT_MODULE_STEM: &str = "__init__";
/// The project-wide audit role directory.
pub const AUDIT_ROLE_DIRECTORY: &str = "audits";
/// The folder-local audit role directory inside a declaration group.
pub const LOCAL_AUDIT_ROLE_DIRECTORY: &str = "_audits";
/// The singular audit directory below an audit role.
pub const SINGULAR_AUDIT_DIRECTORY: &str = "singular";
