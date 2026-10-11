//! Python's `extract_relation_names_impl`.

use crate::relation_names::_helpers::walk::extracted_relations;
use crate::relation_names::errors::RelationNamesFailure;
use crate::relation_names::models::ExtractedRelations;

/// Relations `sql` names and temporary tables it creates; None where the parse fails.
pub fn extract_relation_names(
    sql: &str,
    dialect: Option<&str>,
) -> Result<Option<ExtractedRelations>, RelationNamesFailure> {
    extracted_relations(sql, dialect)
}
