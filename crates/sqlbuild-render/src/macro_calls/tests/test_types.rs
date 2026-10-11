use crate::macro_calls::errors::ScanError;

/// One expected call site: start, end, name, scanned tree names and typed reference text.
pub(crate) type ExpectedSite = (
    usize,
    usize,
    &'static str,
    Option<&'static [&'static str]>,
    bool,
);

/// One expected splice: the rendered SQL and each span's source and output offsets.
pub(crate) type ExpectedSplice = (&'static str, &'static [(usize, usize, usize, usize)]);

pub(crate) struct ScanMacroCallSitesTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_sites: &'static [ExpectedSite],
    pub(crate) expected_failure: Option<(Option<usize>, ScanError)>,
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

pub(crate) struct MacroCallStoreTestCase {
    pub(crate) description: &'static str,
    pub(crate) recorded_class_texts: &'static [&'static str],
    pub(crate) looked_up_class_texts: &'static [&'static str],
    pub(crate) call_text: &'static str,
    pub(crate) expected_store_hit: bool,
}

pub(crate) struct DeepNestingTestCase {
    pub(crate) description: &'static str,
    pub(crate) depth: usize,
    pub(crate) expected_tree_names: &'static [&'static str],
    pub(crate) expected_max_seconds: f64,
}

/// Call names as Python's `_scan_sqlbuild_call_names` returned them, or its scan error.
pub(crate) type ExpectedNames = Result<&'static [&'static str], ScanError>;

pub(crate) struct MacroCallNamesTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_top_level: ExpectedNames,
    pub(crate) expected_nested: ExpectedNames,
}

pub(crate) struct CallBoundsTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_args_starts: &'static [usize],
    pub(crate) expected_failure: Option<(Option<usize>, Option<&'static str>, ScanError)>,
}

pub(crate) struct CallClassStoreTextTestCase {
    pub(crate) description: &'static str,
    pub(crate) context_token: Option<&'static str>,
    pub(crate) prior_relations: Option<&'static [(&'static str, &'static str)]>,
    pub(crate) expected_text: &'static str,
}
