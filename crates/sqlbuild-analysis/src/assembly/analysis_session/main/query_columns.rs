//! Python's per-query column analysis outside the session.

use crate::assembly::analysis_session::_helpers::query_columns as columns;
use crate::assembly::analysis_session::errors::QueryColumnsFailure;
use crate::assembly::analysis_session::models::{QueryColumns, QueryColumnsRequest};
use crate::semantic_validation::models::ProjectCatalog;

/// Each query's columns, in order; `Parse` and `Legacy` SQL is normalized first, in order.
pub fn query_columns(
    catalog: Option<&ProjectCatalog>,
    request: &QueryColumnsRequest,
) -> Result<Vec<QueryColumns>, QueryColumnsFailure> {
    let request: QueryColumnsRequest =
        columns::normalized_request(request).map_err(QueryColumnsFailure::Normalization)?;
    columns::query_columns(catalog, &request).map_err(QueryColumnsFailure::Internal)
}
