//! Compiled SQL test facts from a typed request, test by test.

use crate::compiler::_helpers::sql_tests::assembly;
use crate::compiler::models::{SqlTestAssemblyBatch, SqlTestAssemblyOutcome};

/// Assemble every test of `batch` in request order; a deferred test is Python's to assemble.
pub fn assemble_sql_test_batch(batch: &SqlTestAssemblyBatch) -> Vec<SqlTestAssemblyOutcome> {
    assembly::assemble_batch(batch)
}
