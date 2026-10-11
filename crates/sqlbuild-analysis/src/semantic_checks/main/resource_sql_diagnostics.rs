//! Python's `get_resource_sql_diagnostics`: audit, SQL test and SQL hook findings.

use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::semantic_checks::_helpers::resource_sql::diagnostics::resource_sql_findings;
use crate::semantic_checks::models::{
    ResourceSqlDiagnostic, ResourceSqlFailure, ResourceSqlRequest,
};
use crate::semantic_validation::models::ProjectCatalog;

/// Bind every audit, SQL test and SQL hook body against the closed shapes on `catalog`.
pub fn resource_sql_diagnostics(
    request: &ResourceSqlRequest,
    catalog: &ProjectCatalog,
) -> Result<Vec<ResourceSqlDiagnostic>, ResourceSqlFailure> {
    catch_compiler_panic(|| Ok(resource_sql_findings(request, catalog)))
        .map_err(ResourceSqlFailure::Internal)?
}
