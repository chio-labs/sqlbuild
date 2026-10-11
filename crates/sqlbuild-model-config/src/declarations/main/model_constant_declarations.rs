//! Python's `parse_model_constant_declarations`.

use crate::declarations::_helpers::values::header_constant;
use crate::declarations::errors::DeclarationFailure;
use crate::declarations::models::{ConstantFacts, DeclarationSite};
use crate::sql_values::models::{RawKey, RawSqlValue};

/// The validated constants of a model header's `constants` value.
pub fn model_constant_declarations(
    raw: Option<&RawSqlValue>,
    site: DeclarationSite<'_>,
) -> Result<Vec<ConstantFacts>, DeclarationFailure> {
    let entries = match raw {
        None | Some(RawSqlValue::Null) => return Ok(Vec::new()),
        Some(RawSqlValue::Object(entries)) => entries,
        Some(_) => {
            return Err(DeclarationFailure::Parse(format!(
                "{} model 'constants' must be a mapping",
                site.file_path
            )));
        }
    };
    entries
        .iter()
        .map(|(key, value)| {
            let name = match key {
                RawKey::Str(text) => RawSqlValue::Str(text.clone()),
                RawKey::Other(_) => RawSqlValue::Null,
            };
            header_constant(&name, value, site)
        })
        .collect()
}
