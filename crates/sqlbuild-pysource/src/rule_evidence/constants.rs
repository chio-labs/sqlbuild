//! Module names, file names and pytest attributes custom-rule evidence reads.

pub(crate) const PUBLIC_HARNESS_MODULES: [&str; 2] = ["sqlbuild.rules", "sqlbuild.rules.testing"];
pub(crate) const EVALUATE_RULE: &str = "evaluate_rule";
pub(crate) const RULE_CASE: &str = "RuleCase";
pub(crate) const RULE_KEYWORD: &str = "rule";
pub(crate) const TEST_CASE_KEYWORD: &str = "test_case";
pub(crate) const CONDITION_KEYWORD: &str = "condition";
pub(crate) const INIT_FILE_NAME: &str = "__init__.py";
pub(crate) const RULES_DIRECTORY_NAME: &str = "rules";
pub(crate) const TESTS_DIRECTORY_NAME: &str = "tests";
pub(crate) const PYTHON_SUFFIX: &str = "py";
pub(crate) const STAR_IMPORT_NAME: &str = "*";
pub(crate) const MIN_PARAMETRIZE_ARGUMENTS: usize = 2;
pub(crate) const PARAMETRIZE_ATTRIBUTE: &str = "parametrize";
pub(crate) const PYTEST_MARK_ATTRIBUTE: &str = "mark";
pub(crate) const PYTEST_MODULE_NAME: &str = "pytest";
pub(crate) const SKIP_MARK: &str = "skip";
pub(crate) const SKIPIF_MARK: &str = "skipif";
pub(crate) const TEST_FUNCTION_PREFIX: &str = "test_";
pub(crate) const TEST_FILE_PREFIX: &str = "test_";
pub(crate) const TEST_FILE_SUFFIX: &str = "_test.py";
pub(crate) const TEST_CLASS_PREFIX: &str = "Test";
pub(crate) const FLOAT_ZERO: f64 = 0.0_f64;
/// The modules, and their submodules, custom-rule code may import.
pub(crate) const CUSTOM_RULE_IMPORT_ROOTS: [&str; 29] = [
    "__future__",
    "abc",
    "bisect",
    "collections",
    "copy",
    "dataclasses",
    "decimal",
    "difflib",
    "enum",
    "fnmatch",
    "fractions",
    "functools",
    "graphlib",
    "hashlib",
    "heapq",
    "itertools",
    "json",
    "math",
    "operator",
    "pathlib",
    "re",
    "rules",
    "sqlbuild.rules",
    "statistics",
    "string",
    "textwrap",
    "types",
    "typing",
    "unicodedata",
];
/// The separator between a module and its submodules.
pub(crate) const MODULE_SEPARATOR: char = '.';
