//! Load output labels and widths.

pub(crate) const KIND_WIDTH: usize = 10;
pub(crate) const NAME_WIDTH: usize = 30;
pub(crate) const STATUS_WIDTH: usize = 6;
pub(crate) const SPINNER_NAME_WIDTH: usize = 48;
pub(crate) const LOG_LABEL: &str = "    log  ";
pub(crate) const LOG_CONTINUATION: &str = "         ";
pub(crate) const UPSTREAM_MARK: char = '+';
pub(crate) const SPINNER_FRAMES: [&str; 10] = [
    "\u{280b}", "\u{2819}", "\u{2839}", "\u{2838}", "\u{283c}", "\u{2834}", "\u{2826}", "\u{2827}",
    "\u{2807}", "\u{280f}",
];
pub(crate) const TREE_BRANCH_GLYPH: &str = "\u{251c}\u{2500}\u{2500}";
pub(crate) const TREE_LAST_GLYPH: &str = "\u{2514}\u{2500}\u{2500}";
