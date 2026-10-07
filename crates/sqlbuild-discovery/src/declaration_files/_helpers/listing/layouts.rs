//! The declaration layout of a discovery session, walked once per kind as Python memoizes it.

use crate::declaration_files::models::{DiscoverySession, RetainedLayout};
use crate::declarations::main::declaration_layout::declaration_layout;
use crate::declarations::models::{DeclarationKind, DeclarationLayout};
use crate::models::StageFailure;
use crate::tree::models::ProjectTree;
use std::sync::{Arc, MutexGuard, PoisonError};

/// The layout of `kind` (every kind with `None`), walked the first time the session asks for it.
pub(crate) fn session_layout(
    session: &DiscoverySession,
    tree: &ProjectTree,
    kind: Option<DeclarationKind>,
) -> Arc<Result<DeclarationLayout, StageFailure>> {
    if let Some(retained) = layouts(session)
        .iter()
        .find(|retained| retained.kind == kind)
    {
        return Arc::clone(&retained.layout);
    }
    let layout: Arc<Result<DeclarationLayout, StageFailure>> =
        Arc::new(declaration_layout(tree, kind));
    layouts(session).push(RetainedLayout {
        kind,
        layout: Arc::clone(&layout),
    });
    layout
}

fn layouts(session: &DiscoverySession) -> MutexGuard<'_, Vec<RetainedLayout>> {
    session
        .layouts
        .lock()
        .unwrap_or_else(PoisonError::into_inner)
}
