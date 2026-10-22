//! One streamed janitor action line.

use crate::cli_text::models::CliStyle;
use crate::janitor_text::_helpers::phases::{duration, flow};
use crate::janitor_text::constants::ACTION_WIDTH;
use crate::janitor_text::models::JanitorItemText;

/// Position, action, padded `name -> destination`, status, duration and any error of one action.
#[must_use]
pub fn render_janitor_item_line(
    (index, total): (usize, usize),
    item: &JanitorItemText,
    flow_width: usize,
    style: CliStyle,
) -> String {
    let position: String = format!("{index:>width$}/{total}", width = total.to_string().len());
    let plain_flow: String = flow(&item.name, item.destination.as_deref());
    let styled_flow: String = match &item.destination {
        Some(destination) => format!(
            "{} {} {}",
            style.object_name(&item.name),
            style.muted("->"),
            style.object_name(destination)
        ),
        None => style.object_name(&item.name),
    };
    let plain_width: usize = plain_flow.chars().count();
    let flow_padding: String = " ".repeat(flow_width.max(plain_width) - plain_width);
    let action_padding: String =
        " ".repeat(ACTION_WIDTH.saturating_sub(item.action.chars().count()));
    let status: &str = if item.error.is_some() { "FAIL" } else { "OK" };
    let elapsed: String = item.duration_seconds.map_or_else(String::new, |seconds| {
        format!("  {}", style.muted(&duration(seconds)))
    });
    let error: String = item
        .error
        .as_deref()
        .and_then(|error| error.lines().next())
        .map_or_else(String::new, |error| format!("  {}", style.error(error)));
    format!(
        "  {}  {}{action_padding}  {styled_flow}{flow_padding}  {}{elapsed}{error}",
        style.muted(&position),
        style.accent(&item.action),
        style.status(status)
    )
}
