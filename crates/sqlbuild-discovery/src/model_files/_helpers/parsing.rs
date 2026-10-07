//! Parse one model file: header checks, model-local declaration checks and their messages.

use crate::_helpers::header_keys::{UnsupportedKeys, unsupported_keys_failure};
use crate::model_files::_helpers::locations::header_column_locations;
use crate::model_files::_helpers::output_columns::output_column_locations;
use crate::model_files::models::{DiscoveredModelFile, ModelFileOptions};
use crate::models::{DiscoveryFailure, FailureKind};
use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_sqltext::compiler::main::model_header_byte_matching::match_one_bytes;
use sqlbuild_sqltext::compiler::main::model_header_single_parsing::parse_one;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

const MODEL_STATEMENT: &str = "MODEL()";

fn failure(message: String) -> DiscoveryFailure {
    DiscoveryFailure::new(FailureKind::ModelSql, message)
}

pub(crate) fn parse_model_file(
    file_path: &str,
    contents: String,
    options: &ModelFileOptions,
) -> Result<DiscoveredModelFile, DiscoveryFailure> {
    let Some((header_start, header_end, sql_start)) = match_one_bytes(&contents) else {
        return Err(failure(format!(
            "SQL model '{file_path}' must start with a MODEL(...) header as the first \
             non-whitespace content"
        )));
    };
    let header = &contents[header_start..header_end];
    let (header_values, column_offsets) = match parse_one(header) {
        (_, _, Some(error)) => return Err(syntax_failure(file_path, &error)),
        (Some(AuthoredValue::Map(values)), Some(offsets), None) => (values, offsets),
        _ => {
            return Err(syntax_failure(
                file_path,
                "Native MODEL header parser returned neither values nor an error",
            ));
        }
    };
    let mut removed: Vec<&str> = header_keys(&header_values)
        .filter(|key| contains(&options.removed_keys, key))
        .collect();
    removed.sort_unstable();
    if !removed.is_empty() {
        return Err(failure(format!(
            "MODEL() option(s) {} in '{file_path}' were removed with virtual environments; \
             projects run in direct mode",
            removed.join(", ")
        )));
    }
    let unsupported: Vec<&str> = header_keys(&header_values)
        .filter(|key| !contains(&options.supported_keys, key))
        .collect();
    if !unsupported.is_empty() {
        return Err(unsupported_keys_failure(&UnsupportedKeys {
            kind: FailureKind::ModelSql,
            statement: MODEL_STATEMENT,
            file_path,
            header,
            header_line: contents[..header_start].matches('\n').count() + 1,
            keys: &unsupported,
            supported_keys: &options.supported_keys,
            python: options.python,
        }));
    }
    let query_sql: String = python_strip(&contents[sql_start..]).to_owned();
    if query_sql.is_empty() {
        return Err(failure(format!(
            "SQL model '{file_path}' must contain SQL after MODEL(...)"
        )));
    }
    let header_column_locations =
        header_column_locations(&contents, (header_start, header_end), &column_offsets);
    let output_column_locations = if options.extract_output_column_locations {
        output_column_locations(
            options.python,
            &contents,
            sql_start,
            options.extract_implicit_alias_columns,
        )
    } else {
        Vec::new()
    };
    Ok(DiscoveredModelFile {
        contents,
        header_values,
        header_column_locations,
        output_column_locations,
        query_sql,
    })
}

fn syntax_failure(file_path: &str, error: &str) -> DiscoveryFailure {
    failure(format!(
        "MODEL(...) in '{file_path}' contains invalid SQLBuild header syntax: {error}"
    ))
}

fn header_keys(values: &[(String, AuthoredValue)]) -> impl Iterator<Item = &str> {
    values.iter().map(|(key, _)| key.as_str())
}

fn contains(keys: &[String], key: &str) -> bool {
    keys.iter().any(|candidate| candidate == key)
}
