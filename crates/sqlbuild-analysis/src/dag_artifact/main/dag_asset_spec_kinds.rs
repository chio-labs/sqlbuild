//! The orchestrator kinds of one asset.

use crate::dag_artifact::constants::SQLBUILD_ASSET_KIND;
use crate::dag_artifact::models::AssetSpecKindPolicy;

/// `sqlbuild` plus `view`/`table` for models, the node kind for direct kinds, else nothing more.
#[must_use]
pub fn dag_asset_spec_kinds(
    (kind, materialization_type): (&str, &str),
    policy: &AssetSpecKindPolicy,
) -> Vec<String> {
    let detail: Option<&str> = if kind == policy.model_kind {
        Some(if materialization_type == policy.view_materialization {
            "view"
        } else {
            "table"
        })
    } else if policy.direct_kinds.contains(kind) {
        Some(kind)
    } else {
        None
    };
    std::iter::once(SQLBUILD_ASSET_KIND)
        .chain(detail)
        .map(str::to_owned)
        .collect()
}
