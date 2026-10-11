//! Unqualified reads of SQL-test helper CTE keys in one CTE body.

use crate::assembly::analysis_session::_helpers::dict_walk::helper_parsed_reads;

/// The `keys` (casefolded) `sql` reads, first read first; None where the SQL does not parse.
pub fn sql_test_helper_reads(sql: &str, keys: &[String]) -> Result<Option<Vec<String>>, String> {
    helper_parsed_reads(sql, keys)
}
