//! The options model discovery parses headers with.

use std::collections::BTreeSet;
use std::sync::Arc;

use crate::_helpers::sorted_keys::sorted_keys;
use crate::constants::{REMOVED_SQL_MODEL_HEADER_KEYS, SQL_MODEL_HEADER_KEYS};
use crate::model_files::models::ModelFileOptions;

/// Model header options; `extraction` is `(implicit alias columns, output locations)`.
#[must_use]
pub fn model_file_options(
    extraction: (bool, bool),
    path_filter: Option<Arc<BTreeSet<String>>>,
) -> ModelFileOptions {
    let (extract_implicit_alias_columns, extract_output_column_locations) = extraction;
    ModelFileOptions {
        supported_keys: sorted_keys(&SQL_MODEL_HEADER_KEYS),
        removed_keys: sorted_keys(&REMOVED_SQL_MODEL_HEADER_KEYS),
        extract_implicit_alias_columns,
        extract_output_column_locations,
        path_filter,
    }
}
