//! `MeasurementContract.__post_init__`: the measurement query's named columns and unit.

use sqlbuild_core::text::main::python_strip::python_strip;

/// Whether every named contract field is non-blank, or the measurement audit error text.
pub fn check_measurement_contract(
    value_column: &str,
    sample_count_column: Option<&str>,
    sample_unit: Option<&str>,
) -> Result<(), &'static str> {
    if python_strip(value_column).is_empty() {
        return Err("measurement contract value_column must be non-empty");
    }
    if sample_count_column.is_some_and(|column| python_strip(column).is_empty()) {
        return Err("measurement contract sample_count_column must be non-empty");
    }
    if sample_unit.is_some_and(|unit| python_strip(unit).is_empty()) {
        return Err("measurement contract sample_unit must be non-empty");
    }
    Ok(())
}
