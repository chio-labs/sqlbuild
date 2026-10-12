/// One expected export: name, file index, parameters, line and dependencies.
pub(crate) type ExpectedExport = (
    &'static str,
    usize,
    &'static [&'static str],
    usize,
    &'static [&'static str],
);

/// One expected loadable module: file index, module name and imported project modules.
pub(crate) type ExpectedModule = (usize, &'static str, &'static [&'static str]);

/// The inventory projected to comparable plain values.
pub(crate) type InventoryRows = (
    Vec<(String, usize, Vec<String>, usize, Vec<String>)>,
    Vec<(usize, String)>,
    Option<Vec<(usize, String, Vec<String>)>>,
);

pub(crate) struct InventoryMacroModulesTestCase {
    pub(crate) description: &'static str,
    /// `(relative path, contents)` of each module, in discovery order.
    pub(crate) sources: &'static [(&'static str, &'static str)],
    pub(crate) expected_exports: &'static [ExpectedExport],
    pub(crate) expected_faults: &'static [(usize, &'static str)],
    pub(crate) expected_modules: Option<&'static [ExpectedModule]>,
}

pub(crate) struct NativeParseErrorTestCase {
    pub(crate) description: &'static str,
    pub(crate) sources: &'static [(&'static str, &'static str)],
    pub(crate) expected_message_prefix: &'static str,
}
