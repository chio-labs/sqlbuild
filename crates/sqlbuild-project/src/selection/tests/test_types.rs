use crate::selection::models::{ModelSelectorNames, SelectorExpansion, UnitTestSelectorSplit};
use sqlbuild_analysis::graph::errors::SelectorError;

pub(super) struct UnitTestSplitTestCase {
    pub(super) description: &'static str,
    pub(super) select: Vec<String>,
    pub(super) exclude: Vec<String>,
    pub(super) accepts_unit_tests: bool,
    pub(super) expected_split: Result<UnitTestSelectorSplit, SelectorError>,
}

pub(super) struct ExpansionTestCase {
    pub(super) description: &'static str,
    pub(super) raw: &'static str,
    pub(super) expected_expansion: Result<SelectorExpansion, String>,
}

pub(super) struct ModelSelectorTestCase {
    pub(super) description: &'static str,
    pub(super) term: &'static str,
    pub(super) expected_names: ModelSelectorNames,
}
