//! The header naming the clone origin, destination and resource count.

use crate::cli_text::models::CliStyle;

/// `sqb clone  origin=<o> destination=<d>  (<n> resources)`.
#[must_use]
pub fn render_clone_header(
    (origin, destination): (&str, &str),
    total: usize,
    style: CliStyle,
) -> String {
    let plural: &str = if total == 1 { "" } else { "s" };
    format!(
        "{}  {}{} {}{}  {}",
        style.title("sqb clone"),
        style.label("origin="),
        style.value(origin),
        style.label("destination="),
        style.value(destination),
        style.muted(&format!("({total} resource{plural})"))
    )
}
