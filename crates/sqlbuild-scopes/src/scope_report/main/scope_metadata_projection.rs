//! `scope_metadata_projection`: deterministic, value-free scope metadata of one index.

use sqlbuild_core::json::models::JsonValue;

use crate::scope_report::_helpers::projection::projection;
use crate::scope_report::models::ProjectionIndex;

/// The projection Python's `build_projection` returns, as a JSON object.
#[must_use]
pub fn scope_metadata_projection(index: &ProjectionIndex) -> JsonValue {
    projection(index)
}
