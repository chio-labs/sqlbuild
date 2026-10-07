//! Ownership roots exactly as the Python builder's `_root` and resource roots derive them.

use crate::scope_index::_helpers::paths::normalize_path;
use crate::scope_index::constants::{
    GLOBAL_DECLARATION_DIRECTORIES, PYTHON_FUNCTION_ROOT, RESOURCE_ROOTS, SEED_ROOT,
};
use crate::scope_index::models::{OwnershipRoot, ScopeDeferral};
use crate::scope_index::models::{OwnershipRootKind, ResourceKind, ResourceRoot};

/// The root a resource of `kind` belongs to.
pub(crate) fn resource_root(
    kind: ResourceKind,
    root: ResourceRoot,
) -> Result<OwnershipRoot, ScopeDeferral> {
    Ok(match root {
        ResourceRoot::Kind => OwnershipRoot {
            path: kind_root(kind)
                .ok_or_else(|| ScopeDeferral {
                    reason: format!("no resource root for {}", kind.as_str()),
                })?
                .to_owned(),
            kind: OwnershipRootKind::Resource,
            resource_kind: Some(kind),
        },
        ResourceRoot::Seed => OwnershipRoot {
            path: SEED_ROOT.to_owned(),
            kind: OwnershipRootKind::Global,
            resource_kind: Some(ResourceKind::Seed),
        },
        ResourceRoot::PythonFunction => OwnershipRoot {
            path: PYTHON_FUNCTION_ROOT.to_owned(),
            kind: OwnershipRootKind::Global,
            resource_kind: Some(ResourceKind::Function),
        },
    })
}

/// Python's `_root(path=..., fallback=...)`; the fallback is normalized as the named roles do.
pub(crate) fn declaration_root(
    path: Option<&str>,
    fallback: &str,
) -> Result<OwnershipRoot, ScopeDeferral> {
    let fallback: String = normalize_path(fallback)?;
    let Some(path) = path else {
        return Ok(OwnershipRoot {
            path: fallback,
            kind: OwnershipRootKind::Global,
            resource_kind: None,
        });
    };
    let normalized: String = normalize_path(path)?;
    let is_global: bool = GLOBAL_DECLARATION_DIRECTORIES.contains(&normalized.as_str());
    let resource_kind: Option<ResourceKind> = RESOURCE_ROOTS
        .iter()
        .find(|(_kind, root)| *root == normalized)
        .map(|(kind, _root)| *kind);
    Ok(OwnershipRoot {
        path: normalized,
        kind: if is_global {
            OwnershipRootKind::Global
        } else {
            OwnershipRootKind::Resource
        },
        resource_kind,
    })
}

/// The root path of a resource kind, or `None` for seeds, which only have a global root.
pub(crate) fn kind_root(kind: ResourceKind) -> Option<&'static str> {
    RESOURCE_ROOTS
        .iter()
        .find(|(root_kind, _path)| *root_kind == kind)
        .map(|(_kind, path)| *path)
}
