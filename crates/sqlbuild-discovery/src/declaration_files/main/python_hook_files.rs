//! The public `*.py` files below every Python hook role, with the scope facts of their role.

use crate::declaration_files::_helpers::listing::collection_reads::CollectionSource;
use crate::declaration_files::_helpers::listing::collections::{
    ListedFile, NamedKind, named_declaration_files,
};
use crate::declaration_files::models::{CollectionFailure, DiscoverySession, FileScope};
use crate::tree::models::ProjectTree;

/// Every Python hook file not named with a leading underscore, root by root in path order.
pub fn python_hook_files(
    session: &DiscoverySession,
    tree: &ProjectTree,
) -> Result<Vec<(String, FileScope)>, CollectionFailure> {
    let source = CollectionSource { session, tree };
    Ok(
        named_declaration_files(&source, &[NamedKind::PythonHook], true)?
            .into_iter()
            .filter_map(|(relative_path, scope): ListedFile| Some((relative_path, scope?)))
            .collect(),
    )
}
