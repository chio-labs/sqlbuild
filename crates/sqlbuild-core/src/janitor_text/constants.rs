//! Labels and layout of `sqb janitor` output.

pub(crate) const LABEL_WIDTH: usize = 22;
pub(crate) const TREE_BRANCH_GLYPH: &str = "\u{251c}\u{2500}\u{2500}";
pub(crate) const TREE_LAST_GLYPH: &str = "\u{2514}\u{2500}\u{2500}";
pub(crate) const TREE_CONTINUATION: &str = "\u{2502}   ";
pub(crate) const TREE_BLANK: &str = "    ";
pub(crate) const DEFAULT_ENVIRONMENT: &str = "default";
pub(crate) const DROP_EARLY: &str = "early";
pub(crate) const DROP_EXPIRED: &str = "expired";
pub(crate) const DROP_MISSING: &str = "missing";
pub(crate) const DISABLED_DETAIL: &str = "Janitor is opt-in. It previews stale warehouse objects \
and asks before archiving or deleting anything.";
/// How many entries each preview section shows without `--verbose`.
pub(crate) const PREVIEW_LIMIT: usize = 10;
pub(crate) const VERBOSE_FLAG: &str = "--verbose";
/// The width of the longest janitor action value.
pub(crate) const ACTION_WIDTH: usize = "archived".len();
pub(crate) const RECORDED_ACTION: &str = "recorded";
pub(crate) const DROPPED_ACTION: &str = "dropped";
pub(crate) const SECONDS_PER_MINUTE: u64 = 60;
/// Durations below this many seconds show seconds with two decimals.
pub(crate) const MINUTE_SECONDS: f64 = 60.0;
pub(crate) const SECONDS_PER_HOUR: u64 = 3600;
