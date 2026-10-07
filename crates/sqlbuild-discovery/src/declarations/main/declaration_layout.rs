//! Walk and validate the declaration layout the Python declaration collections read.

use crate::_helpers::pool::discovery_pool;
use crate::declarations::_helpers::declaration_tree::declaration_file_facts;
use crate::declarations::_helpers::named_layout::named_declaration_groups;
use crate::declarations::_helpers::scan::authored_outcome;
use crate::declarations::models::{DeclarationKind, DeclarationLayout};
use crate::models::StageFailure;
use crate::tree::models::ProjectTree;

/// The file facts (of `kind` only, if given) and named declaration groups, valid or failing.
pub fn declaration_layout(
    tree: &ProjectTree,
    kind: Option<DeclarationKind>,
) -> Result<DeclarationLayout, StageFailure> {
    let pool = discovery_pool().map_err(StageFailure::Internal)?;
    pool.install(|| {
        let file_facts = authored_outcome(declaration_file_facts(tree, kind))?;
        let named_groups = authored_outcome(named_declaration_groups(tree))?;
        Ok(DeclarationLayout {
            file_facts,
            named_groups,
        })
    })
}
