//! Python's `parse_enum_declaration_file` for public enum files.

use crate::declaration_files::_helpers::checks::identities::validate_public_identity;
use crate::declaration_files::_helpers::checks::python_values::{
    PythonType, failure, get, is_identifier, python_str, python_type, unknown_keys,
};
use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::declaration_files::_helpers::parsing::declaration_headers::declaration_headers;
use crate::declaration_files::models::{EnumDeclaration, EnumFile};
use crate::models::FailureKind;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

const ENUM_KEYS: [&str; 2] = ["name", "members"];
const VARCHAR_TYPE: &str = "VARCHAR";
const INTEGER_TYPE: &str = "INTEGER";

pub(crate) fn parse_enum_file(file_path: &str, contents: String) -> Result<EnumFile, ParseStop> {
    let declarations: Vec<EnumDeclaration> = declaration_headers(&contents, file_path, "ENUM")?
        .into_iter()
        .map(|header| parse_enum(&header.values, file_path))
        .collect::<Result<_, _>>()?;
    Ok(EnumFile {
        contents,
        declarations,
    })
}

fn declaration(message: String) -> ParseStop {
    failure(FailureKind::Declaration, message)
}

fn parse_enum(
    values: &[(String, AuthoredValue)],
    file_path: &str,
) -> Result<EnumDeclaration, ParseStop> {
    let unknown: Vec<String> = unknown_keys(values, &ENUM_KEYS);
    if !unknown.is_empty() {
        return Err(declaration(format!(
            "{file_path} enum has unknown keys: {}",
            unknown.join(", ")
        )));
    }
    let name: String = declaration_name(get(values, "name"), file_path, "enum")?;
    let members: Vec<(String, AuthoredValue)> = match get(values, "members") {
        Some(AuthoredValue::List(items)) => shorthand_members(items, file_path, &name)?,
        Some(AuthoredValue::Map(items)) => explicit_members(items, file_path, &name)?,
        _ => {
            return Err(declaration(format!(
                "{file_path} enum '{name}' members must use [...] or (...)"
            )));
        }
    };
    if members.is_empty() {
        return Err(declaration(format!(
            "{file_path} enum '{name}' must declare at least one member"
        )));
    }
    if let Some((member, _)) = members
        .iter()
        .find(|(member, _)| *member != member.to_ascii_uppercase())
    {
        return Err(declaration(format!(
            "{file_path} enum '{name}' member identifiers must be uppercase: '{member}'"
        )));
    }
    let mut types: Vec<PythonType> = Vec::with_capacity(members.len());
    for (_, value) in &members {
        types.push(python_type(value)?);
    }
    if types.iter().any(|value_type| *value_type != types[0]) {
        return Err(declaration(format!(
            "{file_path} enum '{name}' members must use one consistent scalar type"
        )));
    }
    Ok(EnumDeclaration {
        name,
        members,
        scalar_type: if types[0] == PythonType::Str {
            VARCHAR_TYPE
        } else {
            INTEGER_TYPE
        },
    })
}

/// `_parse_declaration_name`: a SQL identifier in canonical public snake_case.
pub(crate) fn declaration_name(
    raw_name: Option<&AuthoredValue>,
    file_path: &str,
    kind: &str,
) -> Result<String, ParseStop> {
    let name: Option<&str> = match raw_name {
        Some(value) => python_str(value)?,
        None => None,
    };
    let Some(name) = name.filter(|name| is_identifier(name)) else {
        return Err(declaration(format!(
            "{file_path} {kind} name must be a SQL identifier"
        )));
    };
    validate_public_identity(name, kind, file_path)?;
    Ok(name.to_owned())
}

fn shorthand_members(
    items: &[AuthoredValue],
    file_path: &str,
    enum_name: &str,
) -> Result<Vec<(String, AuthoredValue)>, ParseStop> {
    let mut members: Vec<(String, AuthoredValue)> = Vec::with_capacity(items.len());
    for item in items {
        let Some(member) = python_str(item)?.filter(|member| is_identifier(member)) else {
            return Err(declaration(format!(
                "{file_path} enum '{enum_name}' shorthand members must be identifiers"
            )));
        };
        if members.iter().any(|(seen, _)| seen == member) {
            return Err(declaration(format!(
                "{file_path} enum '{enum_name}' has duplicate member '{member}'"
            )));
        }
        members.push((member.to_owned(), AuthoredValue::String(member.to_owned())));
    }
    Ok(members)
}

fn explicit_members(
    items: &[(String, AuthoredValue)],
    file_path: &str,
    enum_name: &str,
) -> Result<Vec<(String, AuthoredValue)>, ParseStop> {
    let mut members: Vec<(String, AuthoredValue)> = Vec::with_capacity(items.len());
    for (member, value) in items {
        if !is_identifier(member) {
            return Err(declaration(format!(
                "{file_path} enum '{enum_name}' member name must be a SQL identifier"
            )));
        }
        if !matches!(python_type(value)?, PythonType::Str | PythonType::Int) {
            return Err(declaration(format!(
                "{file_path} enum '{enum_name}' member '{member}' value must be a string or \
                 integer"
            )));
        }
        members.push((member.clone(), value.clone()));
    }
    Ok(members)
}
