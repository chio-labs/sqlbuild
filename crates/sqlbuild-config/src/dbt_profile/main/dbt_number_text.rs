//! `dbt_number_text`: how dbt's `as_number` parses text.

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::dbt_profile::constants::DBT_NUMBER_DECIMAL_SEPARATOR;
use crate::dbt_profile::models::DbtNumberParse;

/// The stripped text dbt's `as_number` parses and whether it parses it as a float.
#[must_use]
pub fn dbt_number_text(text: &str) -> (&str, DbtNumberParse) {
    let stripped: &str = python_strip(text);
    let parse: DbtNumberParse = if stripped.contains(DBT_NUMBER_DECIMAL_SEPARATOR) {
        DbtNumberParse::Float
    } else {
        DbtNumberParse::Integer
    };
    (stripped, parse)
}
