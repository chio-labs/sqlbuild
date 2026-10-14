//! The error for a unit-test selector given to a command that does not run unit tests.

use crate::graph::errors::SelectorError;
use crate::planner_selection::constants::{UNIT_TEST_ONLY_TEST_AND_BUILD, UNIT_TEST_SELECTOR_CODE};

/// The coded rejection naming the selector.
pub fn unit_test_selector_rejection(selector: &str) -> SelectorError {
    SelectorError {
        code: UNIT_TEST_SELECTOR_CODE,
        message: format!(
            "selector '{selector}' selects a unit test; {UNIT_TEST_ONLY_TEST_AND_BUILD}"
        ),
        help: None,
    }
}
