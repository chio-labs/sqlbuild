/// Python sources and module moves, and the rewritten sources or refusals they give.
pub(crate) struct ImportRewriteTestCase {
    pub(crate) description: &'static str,
    /// `(path, contents)` of each project Python file.
    pub(crate) sources: &'static [(&'static str, &'static str)],
    /// `(from, to)` of each moved module file.
    pub(crate) moves: &'static [(&'static str, &'static str)],
    /// `(path, contents)` of each source an edit changes, after the edits.
    pub(crate) expected_sources: &'static [(&'static str, &'static str)],
    /// `path:line:column` and the start of the reason of each refusal.
    pub(crate) expected_refusals: &'static [(&'static str, &'static str)],
}
