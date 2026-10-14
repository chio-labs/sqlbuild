pub(super) struct NodeSelectorTestCase {
    pub(super) description: &'static str,
    pub(super) select: &'static [&'static str],
    pub(super) exclude: &'static [&'static str],
    pub(super) expected_names: Result<&'static [&'static str], SelectorFailure>,
}

pub(super) struct RunSelectionTestCase {
    pub(super) description: &'static str,
    pub(super) select: &'static [&'static str],
    pub(super) exclude: &'static [&'static str],
    pub(super) expected_selection: Result<ExpectedRun, SelectorFailure>,
}

pub(super) struct InventoryTestCase {
    pub(super) description: &'static str,
    pub(super) relative_path: &'static str,
    pub(super) expected_folder: &'static str,
}

/// `(sql keys, python node names)` a run selects.
pub(super) type ExpectedRun = (
    &'static [(&'static str, &'static str)],
    &'static [&'static str],
);

/// `(code, message)` of the `PlannerInputError` Python raises.
pub(super) type SelectorFailure = (&'static str, &'static str);
