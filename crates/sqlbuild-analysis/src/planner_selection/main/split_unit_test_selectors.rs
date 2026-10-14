//! Move unit-test selectors out of resource selectors, or reject them for this command.

use std::collections::BTreeSet;

use crate::graph::errors::SelectorError;
use crate::planner_selection::_helpers::unit_test_tokens::split_groups;
use crate::planner_selection::models::{
    SelectorGroups, UnitTestSelectorNames, UnitTestSelectorSplit,
};

/// The resource selectors left and the unit tests selected or excluded by name.
pub fn split_unit_test_selectors(
    groups: SelectorGroups<'_>,
    names: &UnitTestSelectorNames,
    accepts_unit_tests: bool,
) -> Result<UnitTestSelectorSplit, SelectorError> {
    let (test_names, select): (BTreeSet<String>, Vec<String>) =
        split_groups(groups.select, names, accepts_unit_tests)?;
    let (excluded_test_names, exclude): (BTreeSet<String>, Vec<String>) =
        split_groups(groups.exclude, names, accepts_unit_tests)?;
    let models_selected: bool =
        groups.select.is_empty() || !select.is_empty() || test_names.is_empty();
    Ok(UnitTestSelectorSplit {
        select,
        exclude,
        test_names,
        excluded_test_names,
        models_selected,
    })
}
