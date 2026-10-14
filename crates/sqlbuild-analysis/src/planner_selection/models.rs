//! Planner selection inputs and results.

use std::collections::BTreeSet;

/// Names selectors can match: unit tests, and every other selectable resource.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct UnitTestSelectorNames {
    pub tests: BTreeSet<String>,
    pub resources: BTreeSet<String>,
}

/// Raw `--select` and `--exclude` groups.
#[derive(Clone, Copy, Debug)]
pub struct SelectorGroups<'a> {
    pub select: &'a [String],
    pub exclude: &'a [String],
}

/// Resource selectors left after unit-test selectors moved into a test selection.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct UnitTestSelectorSplit {
    pub select: Vec<String>,
    pub exclude: Vec<String>,
    pub test_names: BTreeSet<String>,
    pub excluded_test_names: BTreeSet<String>,
    pub models_selected: bool,
}

/// One selector split into `+` expansion flags and core text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SelectorExpansion {
    pub core: String,
    pub upstream: bool,
    pub downstream: bool,
}

/// A model as SQLBuild-owned model selectors see it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SelectableModel {
    pub name: String,
    pub tags: Vec<String>,
    pub folder: String,
}

/// Names one SQLBuild model selector resolves to, and its translated path selector when it changed.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ModelSelectorNames {
    pub names: Vec<String>,
    pub translated: Option<String>,
}
