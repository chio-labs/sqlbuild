//! The `TargetConfig` fields a target layer holds, in order.

use crate::effective::constants::TARGET_FIELDS;
use crate::effective::models::TargetField;

/// Every field of `TargetConfig`, nested dataclass fields under their group.
#[must_use]
pub fn target_fields() -> &'static [TargetField] {
    TARGET_FIELDS
}
