//! Python's `parse_model_enum_declarations`.

use crate::declarations::_helpers::enums::enum_declaration;
use crate::declarations::errors::DeclarationFailure;
use crate::declarations::models::{DeclarationSite, EnumFacts};
use crate::sql_values::models::{RawKey, RawSqlValue};

/// The validated enums of a model header's `enums` value.
pub fn model_enum_declarations(
    raw: Option<&RawSqlValue>,
    site: DeclarationSite<'_>,
) -> Result<Vec<EnumFacts>, DeclarationFailure> {
    let entries = match raw {
        None | Some(RawSqlValue::Null) => return Ok(Vec::new()),
        Some(RawSqlValue::Object(entries)) => entries,
        Some(_) => {
            return Err(DeclarationFailure::Parse(format!(
                "{} model 'enums' must be a mapping",
                site.file_path
            )));
        }
    };
    entries
        .iter()
        .map(|(key, members)| {
            let name = match key {
                RawKey::Str(text) => RawSqlValue::Str(text.clone()),
                RawKey::Other(_) => RawSqlValue::Null,
            };
            enum_declaration(&name, members, site)
        })
        .collect()
}
