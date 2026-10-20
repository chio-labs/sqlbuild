//! `project_source_path`: whether a logging call came from the project's own Python.

use std::path::{Component, Path};

use crate::diagnostic_routing::constants::PACKAGE_DIRECTORIES;

/// Whether `pathname` lies under one of `project_roots` and outside installed packages.
#[must_use]
pub fn project_source_path(pathname: &str, project_roots: &[String]) -> bool {
    let path: &Path = Path::new(pathname);
    project_roots
        .iter()
        .any(|root| !root.is_empty() && path.starts_with(root))
        && !path.components().any(|component| {
            matches!(component, Component::Normal(name)
                if PACKAGE_DIRECTORIES.iter().any(|package| name == *package))
        })
}
