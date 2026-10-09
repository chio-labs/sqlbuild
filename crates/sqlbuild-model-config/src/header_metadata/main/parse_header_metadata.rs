//! Parse one MODEL header's columns and audits, with the errors Python raises.

use crate::header_metadata::_helpers::audits::audit_list;
use crate::header_metadata::_helpers::columns::column_mapping;
use crate::header_metadata::_helpers::text::Site;
use crate::header_metadata::constants::MODEL_LABEL;
use crate::header_metadata::models::HeaderMetadata;
use crate::types::AuthoredNode;

/// Parse the authored `columns` and `audits` of the model file at `path` as Python would.
pub fn parse_header_metadata<N: AuthoredNode>(
    columns: &N,
    audits: &N,
    path: &str,
) -> HeaderMetadata<N> {
    HeaderMetadata {
        columns: column_mapping(columns, path),
        audits: audit_list(
            audits,
            Site {
                path,
                label: MODEL_LABEL,
                column: None,
            },
        ),
    }
}
