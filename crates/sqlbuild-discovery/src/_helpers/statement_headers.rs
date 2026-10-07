//! Parse a statement header and reject its unsupported keys, as Python's discovery does.

use crate::_helpers::header_keys::{UnsupportedKeys, unsupported_keys_failure};
use crate::models::{DiscoveryFailure, FailureKind};
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::compiler::main::model_header_single_parsing::parse_one;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

/// One statement kind's header contract.
pub(crate) struct StatementHeader<'a> {
    pub(crate) kind: FailureKind,
    /// The name in syntax errors, such as `TEST`.
    pub(crate) statement_name: &'a str,
    /// The name in unsupported-key errors, such as `TEST()`.
    pub(crate) statement: &'a str,
    pub(crate) file_path: &'a str,
    pub(crate) supported_keys: &'a [String],
    pub(crate) python: PythonText,
}

/// `parse_header_values` then `reject_unsupported_header_keys`; `header_line` is one-based.
pub(crate) fn parse_statement_header(
    contract: &StatementHeader<'_>,
    header: &str,
    header_line: usize,
) -> Result<Vec<(String, AuthoredValue)>, DiscoveryFailure> {
    let values: Vec<(String, AuthoredValue)> = match parse_one(header) {
        (_, _, Some(error)) => return Err(syntax_failure(contract, &error)),
        (Some(AuthoredValue::Map(values)), _, None) => values,
        _ => {
            return Err(syntax_failure(
                contract,
                "Native MODEL header parser returned neither values nor an error",
            ));
        }
    };
    let unsupported: Vec<&str> = values
        .iter()
        .map(|(key, _)| key.as_str())
        .filter(|key| !is_supported(contract.supported_keys, key))
        .collect();
    if unsupported.is_empty() {
        return Ok(values);
    }
    Err(unsupported_keys_failure(&UnsupportedKeys {
        kind: contract.kind,
        statement: contract.statement,
        file_path: contract.file_path,
        header,
        header_line,
        keys: &unsupported,
        supported_keys: contract.supported_keys,
        python: contract.python,
    }))
}

fn syntax_failure(contract: &StatementHeader<'_>, error: &str) -> DiscoveryFailure {
    DiscoveryFailure::new(
        contract.kind,
        format!(
            "{}(...) in '{}' contains invalid SQLBuild header syntax: {error}",
            contract.statement_name, contract.file_path
        ),
    )
}

fn is_supported(supported_keys: &[String], key: &str) -> bool {
    supported_keys.iter().any(|supported| supported == key)
}
