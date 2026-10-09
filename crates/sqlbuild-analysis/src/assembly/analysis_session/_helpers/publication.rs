//! Python's `published_model_shape` and `inferred_binding_shape`.

use std::collections::HashMap;

use crate::assembly::analysis_session::_helpers::catalog_state::SessionCatalog;
use crate::assembly::analysis_session::_helpers::mappings::{
    catalog_columns, catalog_relations, with_pair,
};
use crate::assembly::analysis_session::constants::{QUOTED_IDENTIFIER_DELIMITER, UNKNOWN_TYPE};
use crate::assembly::analysis_session::types::{Pairs, Shapes};
use crate::semantic_validation::main::normalize::normalize_analysis_sql;
use crate::semantic_validation::models::NormalizationInput;

/// How a session publishes relation shapes.
pub(crate) struct ShapeOptions<'a> {
    pub(crate) dialect: &'a str,
    pub(crate) case_sensitive: bool,
}

/// One relation's inferred columns and the SQL and inputs they came from.
pub(crate) struct ShapeSource<'a> {
    pub(crate) sql: &'a str,
    pub(crate) columns: Pairs,
    pub(crate) inputs: &'a Shapes,
    pub(crate) snapshot_columns: Option<&'a (String, String)>,
}

impl SessionCatalog {
    /// A model relation's shape, including snapshot validity columns.
    pub(crate) fn published_model_shape(
        &self,
        options: &ShapeOptions<'_>,
        source: ShapeSource<'_>,
    ) -> Result<Pairs, String> {
        let snapshot_columns: Option<&(String, String)> = source.snapshot_columns;
        let mut shape: Pairs = self.inferred_binding_shape(options, source)?;
        if let Some((valid_from, valid_to)) = snapshot_columns {
            shape = with_pair(shape, valid_from, UNKNOWN_TYPE);
            shape = with_pair(shape, valid_to, UNKNOWN_TYPE);
        }
        Ok(shape)
    }

    /// Column names keep authored quoting only where the dialect binds quoted names exactly.
    pub(crate) fn inferred_binding_shape(
        &self,
        options: &ShapeOptions<'_>,
        source: ShapeSource<'_>,
    ) -> Result<Pairs, String> {
        if !options.case_sensitive {
            return Ok(source.columns);
        }
        let normalized: String = normalize_analysis_sql(NormalizationInput {
            sql: source.sql.to_owned(),
            dialect: options.dialect.to_owned(),
            stubs: HashMap::new(),
            placeholders: HashMap::new(),
        })?;
        if !normalized.contains(QUOTED_IDENTIFIER_DELIMITER) && !has_exact_input(source.inputs) {
            return Ok(source.columns);
        }
        Ok(self
            .native
            .inferred_schema(
                &normalized,
                catalog_columns(&source.columns),
                catalog_relations(source.inputs),
            )?
            .into_iter()
            .map(|(name, data_type)| (name, data_type.unwrap_or_default()))
            .collect())
    }
}

fn has_exact_input(inputs: &Shapes) -> bool {
    inputs
        .iter()
        .flat_map(|(_, shape)| shape.iter())
        .any(|(name, _)| name.contains(QUOTED_IDENTIFIER_DELIMITER))
}
