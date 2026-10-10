pub(super) struct SelectorTestCase {
    pub(super) description: &'static str,
    pub(super) select: &'static [&'static str],
    pub(super) exclude: &'static [&'static str],
    pub(super) expected_keys: &'static [(&'static str, &'static str)],
}

pub(super) struct SelectorErrorTestCase {
    pub(super) description: &'static str,
    pub(super) select: &'static [&'static str],
    pub(super) exclude: &'static [&'static str],
    pub(super) expected_error: SelectorFailure,
}

/// `(code, message, help)` of the `PlannerInputError` Python raises.
pub(super) type SelectorFailure = (&'static str, &'static str, Option<&'static str>);

pub(super) struct GlobTestCase {
    pub(super) description: &'static str,
    pub(super) pattern: &'static str,
    pub(super) name: &'static str,
    pub(super) expected_match: bool,
}

pub(super) struct CloseMatchTestCase {
    pub(super) description: &'static str,
    pub(super) word: &'static str,
    pub(super) candidates: &'static [&'static str],
    pub(super) cutoff: f64,
    pub(super) expected_matches: &'static [&'static str],
}
