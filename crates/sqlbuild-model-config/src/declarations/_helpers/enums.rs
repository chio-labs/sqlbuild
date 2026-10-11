//! `_parse_enum_declaration` for model-header enums.

use crate::declarations::_helpers::names::{declaration_name, identifier, is_identifier};
use crate::declarations::constants::{INTEGER_TYPE, VARCHAR_TYPE};
use crate::declarations::errors::DeclarationFailure;
use crate::declarations::models::{DeclarationSite, EnumFacts, EnumValue};
use crate::sql_values::models::{RawKey, RawSqlValue};

type Members = Result<Vec<(String, EnumValue)>, DeclarationFailure>;

fn parse(message: String) -> DeclarationFailure {
    DeclarationFailure::Parse(message)
}

fn shorthand(raw: &[RawSqlValue], file_path: &str, enum_name: &str) -> Members {
    let mut members: Vec<(String, EnumValue)> = Vec::new();
    for member in raw {
        let RawSqlValue::Str(name) = member else {
            return Err(parse(format!(
                "{file_path} enum '{enum_name}' shorthand members must be identifiers"
            )));
        };
        if !is_identifier(name) {
            return Err(parse(format!(
                "{file_path} enum '{enum_name}' shorthand members must be identifiers"
            )));
        }
        if members.iter().any(|(seen, _)| seen == name) {
            return Err(parse(format!(
                "{file_path} enum '{enum_name}' has duplicate member '{name}'"
            )));
        }
        members.push((name.clone(), EnumValue::Text(name.clone())));
    }
    Ok(members)
}

fn explicit(raw: &[(RawKey, RawSqlValue)], file_path: &str, enum_name: &str) -> Members {
    raw.iter()
        .map(|(key, value)| {
            let key = match key {
                RawKey::Str(text) => RawSqlValue::Str(text.clone()),
                RawKey::Other(_) => RawSqlValue::Null,
            };
            let name = identifier(&key, file_path, &format!("enum '{enum_name}' member"))?;
            let value = match value {
                RawSqlValue::Str(text) => EnumValue::Text(text.clone()),
                RawSqlValue::Int(number) => EnumValue::Integer(number.to_string()),
                RawSqlValue::BigInt(digits) => EnumValue::Integer(digits.clone()),
                _ => {
                    return Err(parse(format!(
                        "{file_path} enum '{enum_name}' member '{name}' value must be a string or integer"
                    )));
                }
            };
            Ok((name, value))
        })
        .collect()
}

/// One validated model-header enum named by `raw_name`.
pub(crate) fn enum_declaration(
    raw_name: &RawSqlValue,
    raw_members: &RawSqlValue,
    site: DeclarationSite<'_>,
) -> Result<EnumFacts, DeclarationFailure> {
    let file_path = site.file_path;
    let name = declaration_name(raw_name, site, "enum")?;
    let members = match raw_members {
        RawSqlValue::List(items) => shorthand(items, file_path, &name)?,
        RawSqlValue::Object(entries) => explicit(entries, file_path, &name)?,
        _ => {
            return Err(parse(format!(
                "{file_path} enum '{name}' members must use [...] or (...)"
            )));
        }
    };
    let Some((_, first)) = members.first() else {
        return Err(parse(format!(
            "{file_path} enum '{name}' must declare at least one member"
        )));
    };
    if let Some((member, _)) = members
        .iter()
        .find(|(member, _)| *member != member.to_ascii_uppercase())
    {
        return Err(parse(format!(
            "{file_path} enum '{name}' member identifiers must be uppercase: '{member}'"
        )));
    }
    let is_text = matches!(first, EnumValue::Text(_));
    if members
        .iter()
        .any(|(_, value)| matches!(value, EnumValue::Text(_)) != is_text)
    {
        return Err(parse(format!(
            "{file_path} enum '{name}' members must use one consistent scalar type"
        )));
    }
    let scalar_type = if is_text { VARCHAR_TYPE } else { INTEGER_TYPE };
    Ok(EnumFacts {
        name,
        members,
        scalar_type,
    })
}
