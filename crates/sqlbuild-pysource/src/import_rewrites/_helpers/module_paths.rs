//! Dotted module names of project files, relative import resolution, and import spelling.

use crate::import_rewrites::constants::{
    MODULE_SEPARATOR, PACKAGE_INIT_STEM, PATH_SEPARATOR, PYTHON_SUFFIX, SHALLOW_RELATIVE_LEVEL,
};

/// The dotted module a project-relative `.py` path imports as, or `None` for other files.
pub(crate) fn module_parts(path: &str) -> Option<Vec<String>> {
    let stem: &str = path.strip_suffix(PYTHON_SUFFIX)?;
    let mut parts: Vec<String> = stem.split(PATH_SEPARATOR).map(str::to_owned).collect();
    if parts.last().is_some_and(|last| last == PACKAGE_INIT_STEM) {
        parts.pop();
    }
    (!parts.is_empty() && parts.iter().all(|part| !part.is_empty())).then_some(parts)
}

/// The package a file's relative imports start from: the folder parts of its path.
pub(crate) fn package_parts(path: &str) -> Vec<String> {
    let mut parts: Vec<String> = path.split(PATH_SEPARATOR).map(str::to_owned).collect();
    parts.pop();
    parts
}

/// Dotted parts of a dotted name.
pub(crate) fn dotted_parts(name: &str) -> Vec<String> {
    if name.is_empty() {
        return Vec::new();
    }
    name.split(MODULE_SEPARATOR).map(str::to_owned).collect()
}

/// A dotted name from its parts.
pub(crate) fn dotted(parts: &[String]) -> String {
    parts.join(&MODULE_SEPARATOR.to_string())
}

/// The module `from <level dots><module>` reads from `package`; `None` above the top package.
pub(crate) fn resolve_relative(
    package: &[String],
    level: usize,
    module: &[String],
) -> Option<Vec<String>> {
    if level == 0 {
        return Some(module.to_vec());
    }
    let climb: usize = level - 1;
    if climb >= package.len() {
        return None;
    }
    let mut parts: Vec<String> = package[..package.len() - climb].to_vec();
    parts.extend(module.iter().cloned());
    Some(parts)
}

/// `target` as a `from` import in `package` spells it: relative when close, else absolute.
pub(crate) fn spell_from_target(
    package: &[String],
    target: &[String],
    original_level: usize,
) -> String {
    if original_level == 0 {
        return dotted(target);
    }
    let common: usize = package
        .iter()
        .zip(target)
        .take_while(|(left, right)| left == right)
        .count();
    let level: usize = package.len() - common + 1;
    if common == 0 || level > original_level.max(SHALLOW_RELATIVE_LEVEL) {
        return dotted(target);
    }
    format!(
        "{}{}",
        MODULE_SEPARATOR.to_string().repeat(level),
        dotted(&target[common..])
    )
}
