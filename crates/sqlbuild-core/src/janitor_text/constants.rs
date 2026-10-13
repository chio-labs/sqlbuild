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
