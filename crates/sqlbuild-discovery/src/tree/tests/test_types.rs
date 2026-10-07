pub(super) struct GlobTestCase {
    pub(super) description: &'static str,
    pub(super) files: &'static [&'static str],
    pub(super) directories: &'static [&'static str],
    /// Symbolic links as `(link, target)`, both relative to the project.
    pub(super) links: &'static [(&'static str, &'static str)],
    pub(super) suffix: &'static str,
    pub(super) expected_paths: &'static [&'static str],
}
