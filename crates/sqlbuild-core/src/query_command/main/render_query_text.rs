//! Query rows as text: a box when they fit, one record per row otherwise.

use crate::query_command::_helpers::boxed::boxed_lines;
use crate::query_command::_helpers::footer::footer;
use crate::query_command::_helpers::long::long_text;
use crate::query_command::models::{QueryDisplay, QueryLayout};

/// The rows in `layout`, then the row count. A fitted layout never drops columns or rows: a result wider than the width, or with a value spanning lines, prints one record per row.
#[must_use]
pub fn render_query_text(display: &QueryDisplay, layout: QueryLayout) -> String {
    let QueryLayout::Fitted { width } = layout else {
        return long_text(display);
    };
    let Some(mut lines) = boxed_lines(display, width) else {
        return long_text(display);
    };
    lines.extend(footer(display));
    format!("{}\n", lines.join("\n"))
}
