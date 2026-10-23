//! The names project packages bind in their `__init__.py`.

use ruff_python_ast::{Alias, Expr, Stmt};

use crate::import_rewrites::_helpers::module_paths::module_parts;
use crate::import_rewrites::constants::{MODULE_SEPARATOR, PACKAGE_INIT_FILE};
use crate::import_rewrites::models::PythonSource;
use crate::import_rewrites::types::PackageBindings;
use crate::module_parse::main::parse_python_module::parse_python_module;

/// Names each parseable `__init__.py` among `sources` binds at module level, by package parts.
pub(crate) fn package_bindings(sources: &[PythonSource]) -> PackageBindings {
    let mut bindings: PackageBindings = PackageBindings::new();
    for source in sources {
        let is_init: bool = source
            .path
            .rsplit('/')
            .next()
            .is_some_and(|name| name == PACKAGE_INIT_FILE);
        let (true, Some(package), Ok(module)) = (
            is_init,
            module_parts(&source.path),
            parse_python_module(&source.contents),
        ) else {
            continue;
        };
        bindings.insert(package, module.body.iter().flat_map(bound_names).collect());
    }
    bindings
}

/// The names `statement` binds at module level, through `if`, `try` and `with` blocks.
fn bound_names(statement: &Stmt) -> Vec<String> {
    match statement {
        Stmt::FunctionDef(function) => vec![function.name.as_str().to_owned()],
        Stmt::ClassDef(class) => vec![class.name.as_str().to_owned()],
        Stmt::Assign(assign) => assign.targets.iter().flat_map(target_names).collect(),
        Stmt::AnnAssign(assign) => target_names(&assign.target),
        Stmt::AugAssign(assign) => target_names(&assign.target),
        Stmt::Import(import) => import.names.iter().map(imported_module_binding).collect(),
        Stmt::ImportFrom(import) => import
            .names
            .iter()
            .map(|alias| {
                alias
                    .asname
                    .as_ref()
                    .unwrap_or(&alias.name)
                    .as_str()
                    .to_owned()
            })
            .collect(),
        Stmt::If(branch) => branch
            .body
            .iter()
            .chain(
                branch
                    .elif_else_clauses
                    .iter()
                    .flat_map(|clause| &clause.body),
            )
            .flat_map(bound_names)
            .collect(),
        Stmt::Try(block) => block
            .body
            .iter()
            .chain(&block.orelse)
            .chain(&block.finalbody)
            .flat_map(bound_names)
            .collect(),
        Stmt::With(block) => block.body.iter().flat_map(bound_names).collect(),
        _ => Vec::new(),
    }
}

/// The name `import a.b [as c]` binds: `c`, or `a`.
fn imported_module_binding(alias: &Alias) -> String {
    match &alias.asname {
        Some(asname) => asname.as_str().to_owned(),
        None => alias
            .name
            .as_str()
            .split(MODULE_SEPARATOR)
            .next()
            .unwrap_or_default()
            .to_owned(),
    }
}

/// The plain names an assignment target binds.
fn target_names(target: &Expr) -> Vec<String> {
    match target {
        Expr::Name(name) => vec![name.id.as_str().to_owned()],
        Expr::Tuple(tuple) => tuple.elts.iter().flat_map(target_names).collect(),
        Expr::List(list) => list.elts.iter().flat_map(target_names).collect(),
        _ => Vec::new(),
    }
}
