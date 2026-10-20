use crate::models::FailureKind;
use crate::project_validation::models::{CsvSettings, ProjectFacts};

/// Python's default `csv.field_size_limit()`.
pub(super) const LIMIT: usize = 131_072;

/// One seed CSV text and the header Python's `csv` reader returns or the error it raises.
pub(super) struct CsvHeaderTestCase {
    pub(super) description: &'static str,
    pub(super) text: String,
    pub(super) settings: CsvSettings,
    pub(super) field_limit: usize,
    pub(super) expected_header: Result<Vec<String>, String>,
}

/// One project's facts and the first failure Python's validation reports, if any.
pub(super) struct ValidationTestCase {
    pub(super) description: &'static str,
    pub(super) facts: ProjectFacts,
    pub(super) expected_failure: Result<(), String>,
}

/// One seed CSV beside a declaration of `declared_columns`, and the failure validation reports.
pub(super) struct SeedHeaderTestCase {
    pub(super) description: &'static str,
    pub(super) csv_text: &'static str,
    pub(super) declared_columns: &'static [&'static str],
    pub(super) expected_failure: Result<(), String>,
}

/// A header the reader returns.
pub(super) fn header(columns: &[&str]) -> Result<Vec<String>, String> {
    Ok(columns.iter().map(|column| (*column).to_owned()).collect())
}

/// The `_csv.Error` message the reader raises.
pub(super) fn csv_error(message: &str) -> Result<Vec<String>, String> {
    Err(message.to_owned())
}

/// The failure `Display` names for `kind` with `message`.
pub(super) fn failure(kind: FailureKind, message: &str) -> Result<(), String> {
    Err(format!("{kind:?}: {message}"))
}

pub(crate) struct OneDataRowTestCase {
    pub(crate) description: &'static str,
    pub(crate) text: String,
    pub(crate) settings: CsvSettings,
    pub(crate) expected_one_row: bool,
}
