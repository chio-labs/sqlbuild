//! Query output layout.

pub(crate) const RECORD_RULE_WIDTH: usize = 40;
/// Above this many rows the footer suggests aggregating or limiting the query.
pub(crate) const MANY_ROWS: usize = 50;
/// The box layout's borders: corners, tees, crosses and lines.
pub(crate) const BOX_TOP: [char; 3] = ['┌', '┬', '┐'];
pub(crate) const BOX_RULE: [char; 3] = ['├', '┼', '┤'];
pub(crate) const BOX_BOTTOM: [char; 3] = ['└', '┴', '┘'];
pub(crate) const BOX_HORIZONTAL: char = '─';
pub(crate) const BOX_VERTICAL: char = '│';
