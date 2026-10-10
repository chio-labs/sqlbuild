//! Python's per-query column analysis outside the session.

use crate::assembly::analysis_session::_helpers::query_columns as columns;
use crate::assembly::analysis_session::models::{QueryColumns, QueryColumnsRequest};
use crate::semantic_validation::models::ProjectCatalog;

/// Each query's columns, in order; only `Batch` queries read the catalog.
pub fn query_columns(
    catalog: Option<&ProjectCatalog>,
    request: &QueryColumnsRequest,
) -> Result<Vec<QueryColumns>, String> {
    columns::query_columns(catalog, request)
}
