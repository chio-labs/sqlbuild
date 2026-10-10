//! Python's `_simple_projection_facts`: literal types, NULL literals and quoted aliases of a query.

use crate::assembly::analysis_session::_helpers::dict_walk::fixture_projection_facts;
use crate::assembly::analysis_session::models::ProjectionFacts;

/// The facts of the first `SELECT`; empty where the wheel's parse raises `PolyglotError`.
pub fn projection_facts(sql: &str, dialect: Option<&str>) -> Result<ProjectionFacts, String> {
    fixture_projection_facts(sql, dialect)
}
