//! Declaration and member names: SQL identifiers and canonical resource identities.

use crate::declarations::errors::DeclarationFailure;
use crate::declarations::models::DeclarationSite;
use crate::resource_identities::main::resource_identity_failure::resource_identity_failure;
use crate::sql_values::models::RawSqlValue;

/// `^[A-Za-z_][A-Za-z0-9_]*$` under `fullmatch`.
pub(crate) fn is_identifier(text: &str) -> bool {
    let mut characters = text.chars();
    characters
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

/// `_parse_identifier`: a SQL identifier named `label`.
pub(crate) fn identifier(
    raw: &RawSqlValue,
    file_path: &str,
    label: &str,
) -> Result<String, DeclarationFailure> {
    match raw {
        RawSqlValue::Str(text) if is_identifier(text) => Ok(text.clone()),
        _ => Err(DeclarationFailure::Parse(format!(
            "{file_path} {label} name must be a SQL identifier"
        ))),
    }
}

/// `_parse_declaration_name`: an identifier that is also a canonical resource identity.
pub(crate) fn declaration_name(
    raw: &RawSqlValue,
    site: DeclarationSite<'_>,
    kind: &str,
) -> Result<String, DeclarationFailure> {
    let name = identifier(raw, site.file_path, kind)?;
    let private = site.model_name.is_some();
    if let Some((corrected, help)) = resource_identity_failure(&name, private) {
        let owner = if private { "model-local" } else { "public" };
        return Err(DeclarationFailure::Identity(
            format!(
                "Invalid {owner} {kind} identity '{name}' in {}; use snake_case '{corrected}'",
                site.file_path
            ),
            help,
        ));
    }
    Ok(name)
}
