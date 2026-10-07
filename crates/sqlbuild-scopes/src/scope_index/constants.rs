//! Scope layout names, mirroring the Python scope builder and `sqlbuild.compiler.scopes.constants`.

use crate::scope_index::models::ResourceKind;

/// Python's builder `_ROOTS`, in its insertion order.
pub const RESOURCE_ROOTS: [(ResourceKind, &str); 5] = [
    (ResourceKind::Model, "models"),
    (ResourceKind::Test, "tests/unit"),
    (ResourceKind::Scenario, "tests/scenarios"),
    (ResourceKind::Function, "functions/sql"),
    (ResourceKind::Source, "sources"),
];
/// The global root of seed resources.
pub const SEED_ROOT: &str = "seeds";
/// The global root of Python function resources.
pub const PYTHON_FUNCTION_ROOT: &str = "functions/python";
/// Declaration directories whose ownership root is global.
pub const GLOBAL_DECLARATION_DIRECTORIES: [&str; 3] = ["macros", "enums", "constants"];
/// Python's `PATH_SEPARATOR`.
pub const PATH_SEPARATOR: char = '/';
/// Python's `CURRENT_PATH_COMPONENT`.
pub const CURRENT_PATH_COMPONENT: &str = ".";
/// Python's `PARENT_PATH_COMPONENT`.
pub const PARENT_PATH_COMPONENT: &str = "..";
/// The file name a tested macro's folder is resolved through.
pub const MACRO_TEST_LEXICAL_FILE: &str = "__macro_test__.sql";
/// The prefix of the synthetic model identity a lexical path resolves as.
pub const PATH_RESOURCE_PREFIX: &str = "<path:";
/// The suffix of the synthetic model identity a lexical path resolves as.
pub const PATH_RESOURCE_SUFFIX: &str = ">";
