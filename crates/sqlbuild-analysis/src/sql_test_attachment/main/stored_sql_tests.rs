//! One test file's stored SQL-test classifications, read back from the shared scan store.

use crate::compiler::models::SqlTestClassification;
use crate::sql_test_attachment::constants::STORED_MODEL_MODE;

/// The stored classifications when they decode to exactly the file's tests' kinds and modes.
#[must_use]
pub fn stored_sql_tests(value: &[u8], modes: &[&str]) -> Option<Vec<SqlTestClassification>> {
    let stored: Vec<SqlTestClassification> = match serde_json::from_slice(value) {
        Ok(stored) => stored,
        Err(_) => return None,
    };
    let matches: bool = stored.len() == modes.len()
        && stored.iter().zip(modes).all(|(item, mode)| match item {
            SqlTestClassification::Model { mode: stored, .. } => {
                stored == STORED_MODEL_MODE && stored == mode
            }
            SqlTestClassification::Direct { mode: stored, .. } => stored == mode,
            SqlTestClassification::Authored { .. } => false,
        });
    matches.then_some(stored)
}
