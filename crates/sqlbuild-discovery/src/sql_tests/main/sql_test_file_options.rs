//! The options SQL test and scenario discovery parses headers with.

use std::collections::BTreeSet;
use std::sync::Arc;

use crate::_helpers::sorted_keys::sorted_keys;
use crate::constants::{SQL_SCENARIO_HEADER_KEYS, SQL_TEST_HEADER_KEYS};
use crate::sql_tests::models::SqlTestFileOptions;

/// The header keys `TEST` and `SCENARIO` statements accept, discovering only `path_filter`.
#[must_use]
pub fn sql_test_file_options(path_filter: Option<Arc<BTreeSet<String>>>) -> SqlTestFileOptions {
    SqlTestFileOptions {
        test_keys: sorted_keys(&SQL_TEST_HEADER_KEYS),
        scenario_keys: sorted_keys(&SQL_SCENARIO_HEADER_KEYS),
        path_filter,
    }
}
