//! Python's `parse_model_schema_declaration_file` up to the columns, which Python parses.

use crate::_helpers::locations::header_column_locations;
use crate::declaration_files::_helpers::checks::python_values::{
    PythonType, failure, get, is_identifier, non_empty_str, python_type, unknown_keys,
};
use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::declaration_files::_helpers::parsing::declaration_headers::declaration_headers;
use crate::declaration_files::_helpers::parsing::enum_files::declaration_name;
use crate::declaration_files::models::{SchemaDeclaration, SchemaFile};
use crate::models::FailureKind;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

const SCHEMA_KEYS: [&str; 4] = ["name", "description", "extends", "columns"];

pub(crate) fn parse_schema_file(
    file_path: &str,
    contents: String,
) -> Result<SchemaFile, ParseStop> {
    let headers = declaration_headers(&contents, file_path, "SCHEMA")?;
    let mut declarations: Vec<SchemaDeclaration> = Vec::with_capacity(headers.len());
    let mut failure: Option<_> = None;
    for header in headers {
        match parse_schema(&header.values, file_path) {
            Ok((name, description, extends)) => declarations.push(SchemaDeclaration {
                name,
                description,
                extends,
                columns: get(&header.values, "columns").cloned(),
                column_locations: header_column_locations(
                    &contents,
                    (header.header_start, header.header_end),
                    &header.column_offsets,
                ),
            }),
            Err(ParseStop::Failed(stopped)) => {
                failure = Some(stopped);
                break;
            }
            Err(ParseStop::Deferred) => return Err(ParseStop::Deferred),
        }
    }
    Ok(SchemaFile {
        contents,
        declarations,
        failure,
    })
}

fn declaration(message: String) -> ParseStop {
    failure(FailureKind::Declaration, message)
}

type SchemaFacts = (String, Option<String>, Option<String>);

fn parse_schema(
    values: &[(String, AuthoredValue)],
    file_path: &str,
) -> Result<SchemaFacts, ParseStop> {
    let unknown: Vec<String> = unknown_keys(values, &SCHEMA_KEYS);
    if !unknown.is_empty() {
        return Err(declaration(format!(
            "{file_path} schema has unknown keys: {}",
            unknown.join(", ")
        )));
    }
    let name: String = declaration_name(get(values, "name"), file_path, "schema")?;
    let description: Option<String> = optional_string(
        get(values, "description"),
        file_path,
        &format!("schema '{name}' description"),
    )?;
    let extends: Option<String> = optional_string(
        get(values, "extends"),
        file_path,
        &format!("schema '{name}' extends"),
    )?;
    if let Some(parent) = &extends
        && !is_identifier(parent)
    {
        return Err(declaration(format!(
            "{file_path} schema '{name}' extends must be an identifier"
        )));
    }
    Ok((name, description, extends))
}

/// `_parse_optional_declaration_string`: absent or `null`, or a non-empty string.
fn optional_string(
    raw_value: Option<&AuthoredValue>,
    file_path: &str,
    label: &str,
) -> Result<Option<String>, ParseStop> {
    let Some(raw_value) = raw_value else {
        return Ok(None);
    };
    if python_type(raw_value)? == PythonType::None {
        return Ok(None);
    }
    match non_empty_str(raw_value)? {
        Some(text) => Ok(Some(text.to_owned())),
        None => Err(declaration(format!(
            "{file_path} {label} must be a non-empty string"
        ))),
    }
}
