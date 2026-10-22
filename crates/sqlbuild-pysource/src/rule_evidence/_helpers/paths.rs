//! Filesystem paths resolved, compared and searched the way `pathlib` does for rule modules.

use std::collections::BTreeSet;
use std::path::{Component, Path, PathBuf};

use ruff_python_ast::Stmt;

use crate::cpython_tree::models::CpythonNode;
use crate::rule_evidence::constants::{INIT_FILE_NAME, PYTHON_SUFFIX, STAR_IMPORT_NAME};
use sqlbuild_core::constants::PYTHON_INIT_MODULE_STEM as INIT_MODULE_NAME;

/// `Path.resolve()`: symlinks resolved through the existing prefix, the rest kept lexically.
pub(crate) fn resolve(path: &Path) -> PathBuf {
    if let Ok(resolved) = std::fs::canonicalize(path) {
        return resolved;
    }
    let Some(parent) = path.parent().filter(|parent| *parent != path) else {
        return path.to_path_buf();
    };
    let base: PathBuf = resolve(parent);
    match path.components().next_back() {
        Some(Component::ParentDir) => base.parent().map_or(base.clone(), Path::to_path_buf),
        Some(Component::CurDir) | None => base,
        Some(component) => base.join(component.as_os_str()),
    }
}

fn is_file(path: &Path) -> bool {
    path.is_file()
}

/// `base.joinpath(*parts)`'s module file, if it resolves under the rules root.
fn module_file(base: &Path, parts: &[String], rules_root: &Path) -> Option<PathBuf> {
    let candidate: PathBuf = parts
        .iter()
        .fold(base.to_path_buf(), |path, part| path.join(part));
    let package: PathBuf = candidate.join(INIT_FILE_NAME);
    let module: Option<PathBuf> =
        (!parts.is_empty()).then(|| candidate.with_extension(PYTHON_SUFFIX));
    for path in std::iter::once(package).chain(module) {
        if is_file(&path) {
            let resolved: PathBuf = resolve(&path);
            return resolved.starts_with(rules_root).then_some(resolved);
        }
    }
    None
}

/// Package initializers executed before `path` under the rules root.
pub(crate) fn package_inits(path: &Path, rules_root: &Path) -> Vec<PathBuf> {
    let mut inits: Vec<PathBuf> = Vec::new();
    for parent in path.ancestors().skip(1) {
        if !parent.starts_with(rules_root) {
            break;
        }
        let init: PathBuf = parent.join(INIT_FILE_NAME);
        if !is_file(&init) {
            continue;
        }
        let resolved: PathBuf = resolve(&init);
        if resolved != path && resolved.starts_with(rules_root) {
            inits.push(resolved);
        }
    }
    inits
}

/// Modules under `rules_root` one import executes, from `project` and only `package` when set.
pub(crate) fn local_import_paths(
    node: &CpythonNode<'_>,
    source_path: &Path,
    (project, rules_root): (&Path, &Path),
    package: Option<&str>,
) -> Vec<PathBuf> {
    let project: PathBuf = project.to_path_buf();
    let mut targets: Vec<(PathBuf, Vec<String>)> = Vec::new();
    match node {
        CpythonNode::Stmt(Stmt::Import(import)) => {
            for alias in &import.names {
                let parts: Vec<String> =
                    alias.name.as_str().split('.').map(str::to_owned).collect();
                if package.is_none_or(|package| parts[0] == package) {
                    targets.push((project.clone(), parts));
                }
            }
        }
        CpythonNode::Stmt(Stmt::ImportFrom(import)) => {
            let module_parts: Vec<String> =
                import.module.as_ref().map_or_else(Vec::new, |module| {
                    module.as_str().split('.').map(str::to_owned).collect()
                });
            let mut base: PathBuf = project.clone();
            if import.level > 0 {
                base = source_path
                    .parent()
                    .map_or(PathBuf::new(), Path::to_path_buf);
                for _ in 1..import.level {
                    base = base.parent().map_or(base.clone(), Path::to_path_buf);
                }
            } else if package
                .is_some_and(|package| module_parts.first().map(String::as_str) != Some(package))
            {
                return Vec::new();
            }
            targets.push((base.clone(), module_parts.clone()));
            for alias in &import.names {
                if alias.name.as_str() != STAR_IMPORT_NAME {
                    let mut parts: Vec<String> = module_parts.clone();
                    parts.push(alias.name.as_str().to_owned());
                    targets.push((base.clone(), parts));
                }
            }
        }
        _ => {}
    }
    let mut resolved: Vec<PathBuf> = Vec::new();
    for (base, parts) in targets {
        if let Some(module) = module_file(&base, &parts, rules_root) {
            resolved.extend(package_inits(&module, rules_root));
            resolved.push(module);
        }
    }
    resolved
}

/// Whether each package from `root` down through `packages` has an `__init__.py`.
fn every_package_initialized(root: &Path, packages: &[String]) -> bool {
    let mut package: PathBuf = root.to_path_buf();
    for name in packages {
        package.push(name);
        if !package.join(INIT_FILE_NAME).is_file() {
            return false;
        }
    }
    true
}

/// The dotted names a rule module at `path` can be imported as from the project.
pub(crate) fn module_names(
    path: &Path,
    project_dir: &Path,
    root: &Path,
) -> Option<BTreeSet<String>> {
    let Ok(relative) = path.strip_prefix(root) else {
        return None;
    };
    let mut parts: Vec<String> = relative
        .components()
        .map(|component| component.as_os_str().to_string_lossy().into_owned())
        .collect();
    if let Some(last) = parts.last_mut()
        && let Some(stem) = Path::new(last.as_str()).file_stem()
        && Path::new(last.as_str()).extension().is_some()
    {
        *last = stem.to_string_lossy().into_owned();
    }
    if parts.last().map(String::as_str) == Some(INIT_MODULE_NAME) {
        parts.pop();
    }
    let mut names: BTreeSet<String> = BTreeSet::from([parts.join(".")]);
    for index in 0..parts.len() {
        let package_parts: &[String] = &parts[index..parts.len() - 1];
        let package_root: PathBuf = parts[..index]
            .iter()
            .fold(project_dir.to_path_buf(), |path, part| path.join(part));
        let packaged: bool =
            !package_parts.is_empty() && every_package_initialized(&package_root, package_parts);
        if packaged {
            names.insert(parts[index..].join("."));
        }
    }
    Some(names)
}
