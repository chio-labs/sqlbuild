pub(super) struct LayerMoveTestCase {
    pub(super) description: &'static str,
    pub(super) old_path: &'static str,
    pub(super) new_name: &'static str,
    pub(super) codes: &'static [&'static str],
    pub(super) project_dir: Option<&'static str>,
    pub(super) windows: bool,
    pub(super) expected_command: Option<&'static str>,
    pub(super) expected_folder: Option<&'static str>,
}

pub(super) struct RenderTestCase {
    pub(super) description: &'static str,
    pub(super) old_path: &'static str,
    pub(super) new_name: &'static str,
    pub(super) codes: &'static [&'static str],
    pub(super) expected_text: &'static str,
}

/// Command-line words and a move file, and the pairs or error message they give.
pub(super) struct RefactorPairsTestCase {
    pub(super) description: &'static str,
    pub(super) is_move: bool,
    pub(super) words: &'static [&'static str],
    pub(super) file: Option<&'static str>,
    pub(super) expected_pairs: Result<&'static [(&'static str, &'static str)], &'static str>,
}

/// One diagnostic as `(rule, code, path, message)`.
pub(super) type DiagnosticRow = (bool, &'static str, &'static str, &'static str);

/// The project's errors before and after file moves, and how they compare.
pub(super) struct BaselineComparisonTestCase {
    pub(super) description: &'static str,
    pub(super) before: &'static [DiagnosticRow],
    pub(super) after: &'static [DiagnosticRow],
    /// `(original path, path)` of each moved file.
    pub(super) moves: &'static [(&'static str, &'static str)],
    pub(super) expected_remaining: &'static [&'static str],
    pub(super) expected_resolved: &'static [&'static str],
    pub(super) expected_blocking: &'static [&'static str],
}
