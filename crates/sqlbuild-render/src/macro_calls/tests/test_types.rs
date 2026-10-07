/// One expected call site: start, end, name, tree names and whether typed reference text appears.
pub(crate) type ExpectedSite = (usize, usize, &'static str, &'static [&'static str], bool);

/// One expected splice: the rendered SQL and each span's source and output offsets.
pub(crate) type ExpectedSplice = (&'static str, &'static [(usize, usize, usize, usize)]);

pub(crate) struct ScanMacroCallSitesTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_sites: Option<&'static [ExpectedSite]>,
}

pub(crate) struct SpliceMacroCallsTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) sites: &'static [(usize, usize)],
    pub(crate) outputs: &'static [&'static str],
    pub(crate) expected_splice: Option<ExpectedSplice>,
}

pub(crate) struct MacroCallMemoTestCase {
    pub(crate) description: &'static str,
    pub(crate) class_id: u64,
    pub(crate) call_text: &'static str,
    pub(crate) expected_hit: bool,
}
