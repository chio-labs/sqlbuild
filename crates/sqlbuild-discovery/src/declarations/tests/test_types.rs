pub(super) struct LayoutTestCase {
    pub(super) description: &'static str,
    pub(super) files: &'static [&'static str],
    pub(super) directories: &'static [&'static str],
    /// `(relative path, kind, scope kind, ownership root, owning path, declaration root)`.
    pub(super) expected_facts: Result<&'static [FactRow], &'static str>,
    /// `(canonical root, group directory)`.
    pub(super) expected_groups: Result<&'static [(&'static str, &'static str)], &'static str>,
}

pub(super) type FactRow = (
    &'static str,
    &'static str,
    &'static str,
    &'static str,
    Option<&'static str>,
    &'static str,
);
