//! Dotted macro module and package names, import resolution and scope visibility.

use ruff_python_ast::{Stmt, StmtImportFrom};

use crate::macro_modules::constants::{
    MODULE_SEPARATOR, PATH_ROOTS, STAR_IMPORT_NAME, SUFFIX_MARK,
};
use crate::macro_modules::models::MacroModuleSource;
use crate::macro_modules::types::MacroScopeKind;

/// `".".join(relative_path.with_suffix("").parts)`.
pub(crate) fn module_name(source: &MacroModuleSource) -> String {
    let parts: &[String] = &source.relative_path.parts;
    let mut names: Vec<&str> = parts.iter().map(String::as_str).collect();
    if let Some(last) = names.last_mut()
        && let Some(dot) = last.rfind(SUFFIX_MARK)
        && dot > 0
        && dot < last.len() - SUFFIX_MARK.len_utf8()
    {
        *last = &last[..dot];
    }
    names.join(MODULE_SEPARATOR)
}

/// The dotted declaration root, or the module's first path part.
pub(crate) fn package_name(source: &MacroModuleSource) -> String {
    match &source.declaration_root {
        Some(parts) => parts.join(MODULE_SEPARATOR),
        None => source
            .relative_path
            .parts
            .first()
            .cloned()
            .unwrap_or_default(),
    }
}

/// Whether `imported` names a project macro module, one of its packages, or a project package.
pub(crate) fn is_project_macro_import(
    imported: &str,
    (module_names, package_names): (&[String], &[String]),
) -> bool {
    module_names
        .iter()
        .any(|module| module == imported || is_dotted_child(module, imported))
        || package_names
            .iter()
            .any(|package| imported == package || is_dotted_child(imported, package))
}

fn is_dotted_child(name: &str, parent: &str) -> bool {
    name.strip_prefix(parent)
        .is_some_and(|rest| rest.starts_with(MODULE_SEPARATOR))
}

/// The package parts a relative import of `level` keeps from `current_module`, then `base`.
fn relative_parts(current_module: &str, level: usize, base: &str) -> Vec<String> {
    let mut package: Vec<&str> = current_module.split(MODULE_SEPARATOR).collect();
    package.pop();
    let retained: usize = (package.len() + 1).saturating_sub(level);
    let mut parts: Vec<String> = package
        .iter()
        .take(retained)
        .map(|part| (*part).to_owned())
        .collect();
    if !base.is_empty() {
        parts.extend(base.split(MODULE_SEPARATOR).map(str::to_owned));
    }
    parts
}

/// The absolute module a `from ... import` reads, or `None` when it escapes the top package.
pub(crate) fn resolve_import_from(
    statement: &StmtImportFrom,
    current_module: &str,
) -> Option<String> {
    let base: &str = statement
        .module
        .as_ref()
        .map_or("", |module| module.as_str());
    let level: usize = statement.level as usize;
    if level == 0 {
        return Some(base.to_owned());
    }
    let package_length: usize = current_module.split(MODULE_SEPARATOR).count() - 1;
    if level > package_length {
        return None;
    }
    Some(relative_parts(current_module, level, base).join(MODULE_SEPARATOR))
}

/// Every dotted name an import statement may load: the module, then each imported member.
pub(crate) fn imported_module_names(statement: &Stmt, current_module: &str) -> Vec<String> {
    match statement {
        Stmt::Import(import) => import
            .names
            .iter()
            .map(|alias| alias.name.as_str().to_owned())
            .collect(),
        Stmt::ImportFrom(import) => {
            let base: &str = import.module.as_ref().map_or("", |module| module.as_str());
            let base: String = if import.level == 0 {
                base.to_owned()
            } else {
                relative_parts(current_module, import.level as usize, base).join(MODULE_SEPARATOR)
            };
            let mut names: Vec<String> = Vec::new();
            if !base.is_empty() {
                names.push(base.clone());
            }
            for alias in &import.names {
                if alias.name.as_str() == STAR_IMPORT_NAME {
                    continue;
                }
                names.push(if base.is_empty() {
                    alias.name.as_str().to_owned()
                } else {
                    format!("{base}{MODULE_SEPARATOR}{}", alias.name.as_str())
                });
            }
            names
        }
        _ => Vec::new(),
    }
}

/// Whether a module importing from `imported` can see its macros, by path parts.
pub(crate) fn import_visible(importer: &MacroModuleSource, imported: &MacroModuleSource) -> bool {
    let relative_parent: &[String] = importer
        .relative_path
        .parts
        .split_last()
        .map_or(&[], |(_, parent)| parent);
    let importer_parent: &[String] = importer.owning_path.as_deref().unwrap_or(relative_parent);
    let owner: &[String] = imported.owning_path.as_deref().unwrap_or(&[]);
    match imported.scope_kind {
        MacroScopeKind::Global => true,
        MacroScopeKind::Local => importer_parent == owner,
        MacroScopeKind::Inherited => {
            importer_parent == owner || is_parent_path(owner, importer_parent)
        }
        MacroScopeKind::Private => false,
    }
}

/// Whether `owner` is one of `path.parents`.
fn is_parent_path(owner: &[String], path: &[String]) -> bool {
    let anchored: bool = path
        .first()
        .is_some_and(|first| first.ends_with(PATH_ROOTS));
    let shortest: usize = usize::from(anchored);
    owner.len() >= shortest && owner.len() < path.len() && path.starts_with(owner)
}
