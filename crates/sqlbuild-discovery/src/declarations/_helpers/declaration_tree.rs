//! Python's `_scan_declaration_file_facts`: macro, enum and constant files with scope facts.

use crate::constants::{
    CANONICAL_AUTHORED_ROOTS, DECLARATION_GROUP_DIRECTORY, GLOBAL_DECLARATION_DIRECTORIES,
    LOCAL_DECLARATION_DIRECTORIES, PYTHON_FILE_SUFFIX, PYTHON_INIT_MODULE_STEM,
    SCOPED_DECLARATION_DIRECTORIES, SQL_FILE_SUFFIX,
};
use crate::declarations::_helpers::declaration_groups::validate_declaration_groups;
use crate::declarations::_helpers::paths::{directory_facts, name, parent, stem};
use crate::declarations::_helpers::scan::declaration_failure;
use crate::declarations::errors::ScanError;
use crate::declarations::models::{DeclarationFileFact, DeclarationKind, ScopeKind};
use crate::tree::main::directories::directories;
use crate::tree::main::path_order::compare_posix_text;
use crate::tree::main::rglob::rglob;
use crate::tree::models::ProjectTree;

/// Where a declaration root sits and who owns it.
struct DeclarationRoot<'a> {
    ownership_root: &'a str,
    directory: &'a str,
    owning_path: Option<&'a str>,
    scope_kind: ScopeKind,
}

/// Every declaration file below every macro, enum and constant root, by relative path.
pub(crate) fn declaration_file_facts(
    tree: &ProjectTree,
    kind: Option<DeclarationKind>,
) -> Result<Vec<DeclarationFileFact>, ScanError> {
    validate_declaration_groups(tree)?;
    let mut local: Vec<&str> = LOCAL_DECLARATION_DIRECTORIES.to_vec();
    local.sort_unstable();
    if let Some(directory) = local
        .into_iter()
        .find(|directory| is_kind(kind, directory) && tree.is_dir(directory))
    {
        return Err(declaration_failure(format!(
            "Scoped declaration root {directory}/ must be below a canonical authored root"
        )));
    }
    let mut facts: Vec<DeclarationFileFact> = Vec::new();
    let mut global: Vec<&str> = GLOBAL_DECLARATION_DIRECTORIES.to_vec();
    global.sort_unstable();
    for directory in global {
        if is_kind(kind, directory) && tree.is_dir(directory) {
            facts.extend(files_under_root(
                tree,
                &DeclarationRoot {
                    ownership_root: directory,
                    directory,
                    owning_path: None,
                    scope_kind: ScopeKind::Global,
                },
            )?);
        }
    }
    for root_parts in CANONICAL_AUTHORED_ROOTS {
        let root: String = root_parts.join("/");
        if tree.is_dir(&root) {
            facts.extend(scoped_root_files(tree, &root, root_parts.len(), kind)?);
        }
    }
    facts.sort_by(|left, right| compare_posix_text(&left.relative_path, &right.relative_path));
    Ok(facts)
}

fn scoped_root_files(
    tree: &ProjectTree,
    root: &str,
    root_length: usize,
    kind: Option<DeclarationKind>,
) -> Result<Vec<DeclarationFileFact>, ScanError> {
    let mut facts: Vec<DeclarationFileFact> = Vec::new();
    for directory in directories(tree, root)? {
        let Some((_, scope_kind)) = directory_facts(name(&directory)) else {
            continue;
        };
        if !is_kind(kind, name(&directory)) {
            continue;
        }
        let parts: Vec<&str> = directory.split('/').collect();
        let between: &[&str] = &parts[root_length..parts.len() - 1];
        if between
            .iter()
            .any(|part| SCOPED_DECLARATION_DIRECTORIES.contains(part))
        {
            return Err(nested_root_failure(&directory));
        }
        let mut owning_path: &str = parent(&directory);
        if name(owning_path) == DECLARATION_GROUP_DIRECTORY {
            owning_path = parent(owning_path);
        }
        facts.extend(files_under_root(
            tree,
            &DeclarationRoot {
                ownership_root: root,
                directory: &directory,
                owning_path: Some(owning_path),
                scope_kind,
            },
        )?);
    }
    Ok(facts)
}

/// Whether a declaration directory holds `kind`, or every kind when none is requested.
fn is_kind(kind: Option<DeclarationKind>, directory_name: &str) -> bool {
    match (kind, directory_facts(directory_name)) {
        (None, _) => true,
        (Some(kind), Some((directory_kind, _))) => directory_kind == kind,
        (Some(_), None) => false,
    }
}

fn nested_root_failure(directory: &str) -> ScanError {
    declaration_failure(format!(
        "Declaration root {directory}/ is nested inside another declaration tree"
    ))
}

fn files_under_root(
    tree: &ProjectTree,
    root: &DeclarationRoot<'_>,
) -> Result<Vec<DeclarationFileFact>, ScanError> {
    if let Some(nested) = directories(tree, root.directory)?
        .into_iter()
        .find(|directory| SCOPED_DECLARATION_DIRECTORIES.contains(&name(directory)))
    {
        return Err(nested_root_failure(&nested));
    }
    let Some((kind, _)) = directory_facts(name(root.directory)) else {
        return Ok(Vec::new());
    };
    let suffix: &str = if kind == DeclarationKind::Macro {
        PYTHON_FILE_SUFFIX
    } else {
        SQL_FILE_SUFFIX
    };
    Ok(
        rglob(tree, root.directory, |entry| entry.name.ends_with(suffix))?
            .into_iter()
            .filter(|path| {
                kind != DeclarationKind::Macro || stem(name(path)) != PYTHON_INIT_MODULE_STEM
            })
            .map(|relative_path| DeclarationFileFact {
                relative_path,
                kind,
                scope_kind: root.scope_kind,
                ownership_root: root.ownership_root.to_owned(),
                owning_path: root.owning_path.map(str::to_owned),
                declaration_root: root.directory.to_owned(),
            })
            .collect(),
    )
}
