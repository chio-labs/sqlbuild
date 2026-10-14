//! Choose the dbt executable.

use crate::dbt_cli::constants::DEFAULT_DBT_EXECUTABLE;
use crate::text::main::python_strip::python_strip;

/// The stripped override when it is not blank, else `dbt`.
#[must_use]
pub fn resolve_dbt_executable(override_value: Option<&str>) -> String {
    match override_value.map(python_strip) {
        Some(value) if !value.is_empty() => value.to_owned(),
        _ => DEFAULT_DBT_EXECUTABLE.to_owned(),
    }
}
