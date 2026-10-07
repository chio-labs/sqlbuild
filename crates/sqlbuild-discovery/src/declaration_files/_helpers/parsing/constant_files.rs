//! Python's `parse_constant_declaration_file` up to value normalisation, which Python performs.

use crate::declaration_files::_helpers::checks::python_values::{
    failure, get, python_str, unknown_keys,
};
use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::declaration_files::_helpers::parsing::declaration_headers::declaration_headers;
use crate::declaration_files::_helpers::parsing::enum_files::declaration_name;
use crate::declaration_files::models::{ConstantDeclaration, ConstantFile};
use crate::models::FailureKind;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

const CONSTANT_KEYS: [&str; 4] = ["name", "value", "type", "render_as"];
const WRAPPER_KEYS: [&str; 3] = ["value", "type", "render_as"];
const COLLECTION_RENDERINGS: [&str; 2] = ["value_list", "array"];

pub(crate) fn parse_constant_file(
    file_path: &str,
    contents: String,
) -> Result<ConstantFile, ParseStop> {
    let headers = declaration_headers(&contents, file_path, "CONSTANT")?;
    let mut declarations: Vec<ConstantDeclaration> = Vec::with_capacity(headers.len());
    let mut failure: Option<_> = None;
    for header in headers {
        match parse_constant(&header.values, file_path) {
            Ok(declaration) => declarations.push(declaration),
            Err(ParseStop::Failed(stopped)) => {
                failure = Some(stopped);
                break;
            }
            Err(ParseStop::Deferred) => return Err(ParseStop::Deferred),
        }
    }
    Ok(ConstantFile {
        contents,
        declarations,
        failure,
    })
}

fn declaration(message: String) -> ParseStop {
    failure(FailureKind::Declaration, message)
}

fn parse_constant(
    values: &[(String, AuthoredValue)],
    file_path: &str,
) -> Result<ConstantDeclaration, ParseStop> {
    let unknown: Vec<String> = unknown_keys(values, &CONSTANT_KEYS);
    if !unknown.is_empty() {
        return Err(declaration(format!(
            "{file_path} constant has unknown keys: {}",
            unknown.join(", ")
        )));
    }
    let name: String = declaration_name(get(values, "name"), file_path, "constant")?;
    let mut value: Option<&AuthoredValue> = get(values, "value");
    let mut explicit_type: Option<&AuthoredValue> = get(values, "type");
    let mut render_as: Option<&AuthoredValue> = get(values, "render_as");
    if let Some(AuthoredValue::TypedConstant(arguments)) = value {
        if explicit_type.is_some() || render_as.is_some() {
            return Err(declaration(format!(
                "{file_path} constant '{name}' cannot combine wrapper and outer options"
            )));
        }
        let unknown: Vec<String> = unknown_keys(arguments, &WRAPPER_KEYS);
        if !unknown.is_empty() {
            return Err(declaration(format!(
                "{file_path} constant '{name}' wrapper has unknown keys: {}",
                unknown.join(", ")
            )));
        }
        value = get(arguments, "value");
        explicit_type = get(arguments, "type");
        render_as = get(arguments, "render_as");
    }
    let Some(value) = value else {
        return Err(declaration(format!(
            "{file_path} constant '{name}' is missing required value"
        )));
    };
    let explicit_type: Option<String> =
        constant_option(explicit_type, file_path, &format!("constant '{name}' type"))?;
    let render_as: Option<String> = constant_option(
        render_as,
        file_path,
        &format!("constant '{name}' render_as"),
    )?;
    if let Some(rendering) = &render_as
        && !COLLECTION_RENDERINGS.contains(&rendering.as_str())
    {
        return Err(declaration(format!(
            "{file_path} constant '{name}' render_as must be value_list or array"
        )));
    }
    Ok(ConstantDeclaration {
        name,
        value: value.clone(),
        explicit_type,
        render_as,
    })
}

/// `_parse_constant_option`: absent, or a non-empty string.
fn constant_option(
    raw_value: Option<&AuthoredValue>,
    file_path: &str,
    label: &str,
) -> Result<Option<String>, ParseStop> {
    let Some(raw_value) = raw_value else {
        return Ok(None);
    };
    match python_str(raw_value)? {
        Some(text) if !text.is_empty() => Ok(Some(text.to_owned())),
        _ => Err(declaration(format!(
            "{file_path} {label} must be an identifier"
        ))),
    }
}
