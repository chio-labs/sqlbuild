//! Where a carried declaration file lands inside its destination role folder.

use crate::placement::_helpers::declaration_directory::declaration_file_directory;
use crate::placement::models::PlacementIndex;
use crate::scope_index::models::{DeclarationRecord, ScopeKind};
use sqlbuild_core::posix_path::main::posix_name::posix_name;

/// How the files already in a declaration role folder are laid out.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum RoleLayout {
    Empty,
    Direct,
    Grouped,
    Mixed,
}

/// A carried declaration's path in `directory`, and whether it needs a group it does not have.
pub(crate) fn carried_path(
    index: &PlacementIndex,
    record: &DeclarationRecord,
    directory: &str,
) -> (String, bool) {
    let name: &str = posix_name(&record.path);
    let source: String = declaration_file_directory(
        record.identity.kind,
        record.scope,
        record.owning_path.as_deref(),
        &record.path,
    );
    let relative: &str = record
        .path
        .strip_prefix(&format!("{source}/"))
        .unwrap_or(name);
    let grouped: bool = relative != name;
    match role_layout(index, directory, &record.path) {
        RoleLayout::Direct => (format!("{directory}/{name}"), false),
        RoleLayout::Grouped if !grouped => (format!("{directory}/{name}"), true),
        RoleLayout::Empty | RoleLayout::Grouped | RoleLayout::Mixed => {
            (format!("{directory}/{relative}"), false)
        }
    }
}

/// The layout of the shared declaration files in `directory`, other than the file at `moving`.
fn role_layout(index: &PlacementIndex, directory: &str, moving: &str) -> RoleLayout {
    let prefix: String = format!("{directory}/");
    let mut direct: bool = false;
    let mut grouped: bool = false;
    for record in &index.declarations {
        if record.scope == ScopeKind::Private || record.path == moving {
            continue;
        }
        if let Some(relative) = record.path.strip_prefix(&prefix) {
            if relative.contains('/') {
                grouped = true;
            } else {
                direct = true;
            }
        }
    }
    match (direct, grouped) {
        (false, false) => RoleLayout::Empty,
        (true, false) => RoleLayout::Direct,
        (false, true) => RoleLayout::Grouped,
        (true, true) => RoleLayout::Mixed,
    }
}
