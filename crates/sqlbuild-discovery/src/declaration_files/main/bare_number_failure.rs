//! Bare-word numbers in an authored header value, checked as declaration files check them.

use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::declaration_files::_helpers::checks::python_values::{WordRules, check_bare_numbers};
use crate::declaration_files::_helpers::checks::stops::ParseStop;
use crate::models::DiscoveryFailure;

/// The failure for the first bare word in `value` that is not a valid number, if any.
pub(crate) fn bare_number_failure(
    value: &AuthoredValue,
    python: PythonText,
    file_path: &str,
) -> Result<(), DiscoveryFailure> {
    check_bare_numbers(value, WordRules { python, file_path })
        .map_err(|ParseStop::Failed(failure)| failure)
}
