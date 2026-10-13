//! The ANSI styles, glyphs and limits of human CLI output.

pub(crate) const BOLD: &str = "\x1b[1m";
pub(crate) const DIM: &str = "\x1b[2m";
pub(crate) const RED: &str = "\x1b[38;5;167m";
pub(crate) const GREEN: &str = "\x1b[32m";
pub(crate) const YELLOW: &str = "\x1b[33m";
pub(crate) const BLUE: &str = "\x1b[34m";
pub(crate) const RESET: &str = "\x1b[0m";
pub(crate) const SUCCESS_STATUS_LABELS: [&str; 3] = ["OK", "PASS", "SUCCESS"];
pub(crate) const WARNING_STATUS_LABELS: [&str; 2] = ["WARN", "WARNING"];
pub(crate) const ERROR_STATUS_LABELS: [&str; 3] = ["ERROR", "FAIL", "FAILED"];
pub(crate) const SKIPPED_STATUS_LABELS: [&str; 2] = ["SKIP", "SKIPPED"];
pub(crate) const PHASE_OK_GLYPH: &str = "\u{2713}";
pub(crate) const PHASE_FAIL_GLYPH: &str = "\u{2717}";
pub(crate) const TREE_BRANCH_GLYPH: &str = "\u{251c}\u{2500}\u{2500}";
pub(crate) const TREE_LAST_GLYPH: &str = "\u{2514}\u{2500}\u{2500}";
/// The human report lists at most this many models.
pub(crate) const HUMAN_MODEL_LIMIT: usize = 100;
pub(crate) const MIN_MODEL_NAME_WIDTH: usize = 24;
pub(crate) const MAX_MODEL_NAME_WIDTH: usize = 48;
pub(crate) const STATUS_WIDTH: usize = 4;
/// The semantic notice shows at most this many reasons, and this many models per reason.
pub(crate) const NOTICE_DISPLAY_LIMIT: usize = 10;
/// What `fit` puts in place of the cut tail of a long name.
pub(crate) const ELLIPSIS: &str = "...";
pub(crate) const OPEN_SOURCE: &str = "open source: ";
pub(crate) const OPEN_INPUT: &str = "open input: ";
pub(crate) const INVALID_UPSTREAM: &str = "depends on invalid model ";
pub(crate) const DEFAULT_ACTION: &str =
    "declare the input shape, then run `sqb compile --no-cache`";
