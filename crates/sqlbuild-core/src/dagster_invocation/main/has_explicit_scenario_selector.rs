//! Explicit selectors after `scenario test`.

use crate::dagster_invocation::constants::{SCENARIO_TEST_ARGUMENT_COUNT, SCENARIO_VALUE_FLAGS};

/// Whether `scenario test` arguments name a scenario beyond flags and their values.
#[must_use]
pub fn has_explicit_scenario_selector(args: &[String]) -> bool {
    let mut skip_next: bool = false;
    for argument in args.iter().skip(SCENARIO_TEST_ARGUMENT_COUNT) {
        if skip_next {
            skip_next = false;
            continue;
        }
        if SCENARIO_VALUE_FLAGS.contains(&argument.as_str()) {
            skip_next = true;
            continue;
        }
        if argument.starts_with('-') {
            continue;
        }
        return true;
    }
    false
}
