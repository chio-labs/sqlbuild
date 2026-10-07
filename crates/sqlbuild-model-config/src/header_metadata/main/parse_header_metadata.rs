//! Parse one MODEL header's columns and audits, or defer to Python.

use crate::header_metadata::_helpers::audits::audit_list;
use crate::header_metadata::_helpers::columns::column_mapping;
use crate::header_metadata::models::{HeaderMetadata, HeaderMetadataDeferral};
use crate::types::AuthoredNode;

/// Parse the authored `columns` and `audits` values exactly as the Python compiler would.
pub fn parse_header_metadata<N: AuthoredNode>(
    columns: &N,
    audits: &N,
) -> Result<HeaderMetadata<N>, HeaderMetadataDeferral> {
    Ok(HeaderMetadata {
        columns: column_mapping(columns)?,
        audits: audit_list(audits)?,
    })
}
