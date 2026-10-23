//! Names, suffixes and limits of Python import rewriting.

/// Separator of dotted module names.
pub(crate) const MODULE_SEPARATOR: char = '.';
/// Separator of project-relative POSIX paths.
pub(crate) const PATH_SEPARATOR: char = '/';
/// The suffix of Python module files.
pub(crate) const PYTHON_SUFFIX: &str = ".py";
/// The stem of a package's own module file.
pub(crate) const PACKAGE_INIT_STEM: &str = "__init__";
/// The file name of a package's own module.
pub(crate) const PACKAGE_INIT_FILE: &str = "__init__.py";
/// The alias name of a star import.
pub(crate) const STAR_IMPORT_NAME: &str = "*";
/// The keyword that starts a `from ... import` statement.
pub(crate) const FROM_KEYWORD: &str = "from";
/// The deepest relative import a rewrite writes when the original was shallower.
pub(crate) const SHALLOW_RELATIVE_LEVEL: usize = 2;
/// Built-in and `importlib` functions that import a module named by a string.
pub(crate) const DYNAMIC_IMPORT_FUNCTIONS: [&str; 2] = ["__import__", "import_module"];
