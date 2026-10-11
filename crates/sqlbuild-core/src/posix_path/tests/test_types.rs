pub(super) struct PosixPathTestCase {
    pub(super) description: &'static str,
    pub(super) path: &'static str,
    pub(super) expected_parts: &'static [&'static str],
    pub(super) expected_parent: &'static str,
    pub(super) expected_name: &'static str,
    /// `suffix` under Python 3.12 and under Python 3.14.
    pub(super) expected_suffixes: (&'static str, &'static str),
}
