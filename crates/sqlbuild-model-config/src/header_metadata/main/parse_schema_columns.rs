//! Parse one MODEL or SCHEMA columns mapping with the errors Python raises.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::columns::column_mapping;
use crate::header_metadata::models::{ColumnRequest, ParsedColumn};
use crate::types::AuthoredNode;

/// The columns of `columns` read as `request` describes, or the first error Python raises.
pub fn parse_schema_columns<N: AuthoredNode>(
    columns: &N,
    request: ColumnRequest<'_>,
) -> Result<Vec<ParsedColumn<N>>, ConfigError> {
    column_mapping(columns, request)
}
