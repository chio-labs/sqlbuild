//! Markers, labels and option defaults of `sqb scope` text output.

pub(crate) const USED_MARKER: &str = "\u{25cf}";
pub(crate) const UNUSED_MARKER: &str = "\u{25cb}";
pub(crate) const LEGEND_MARKERS: &str =
    "\u{25cf} used by this resource   \u{25cb} not used by this resource";
pub(crate) const LEGEND_VERBOSE_HINT: &str = "--verbose for scope details";
pub(crate) const BRANCH_CONNECTOR: &str = "\u{251c}\u{2500}";
pub(crate) const LAST_CONNECTOR: &str = "\u{2514}\u{2500}";
pub(crate) const CURRENT_DIRECTORY: &str = ".";
pub(crate) const NONE_TEXT: &str = "(none)";
pub(crate) const PATH_RELATIVE: &str = "relative";
pub(crate) const PATH_COMPACT: &str = "compact";
pub(crate) const PATH_NONE: &str = "none";
pub(crate) const GLOBAL_SUMMARY: &str = "summary";
pub(crate) const GLOBAL_ALL: &str = "all";
pub(crate) const DEFAULT_PAGE_SIZE: i64 = 100;
pub(crate) const ERROR_SEVERITY: &str = "error";
/// Scope kinds and the label each reads as.
pub(crate) const SCOPE_LABELS: [(&str, &str); 4] = [
    ("global", "project"),
    ("inherited", "descendant-public"),
    ("local", "exact-owner-private"),
    ("private", "model-private"),
];
