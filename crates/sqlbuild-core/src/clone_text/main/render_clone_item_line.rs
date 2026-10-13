//! One streamed clone progress line.

use crate::cli_text::models::CliStyle;
use crate::clone_text::_helpers::quoted::clone_relation_display_name;
use crate::clone_text::constants::ACTION_WIDTH;
use crate::clone_text::main::clone_relation_flow_text::clone_relation_flow_text;
use crate::clone_text::models::{CloneItemText, CloneStatusKind};

/// Position, action, origin to destination padded to `relation_width`, status and duration.
#[must_use]
pub fn render_clone_item_line(
    (index, total): (usize, usize),
    item: &CloneItemText,
    relation_width: usize,
    style: CliStyle,
) -> String {
    let position: String = format!("{index:>width$}/{total}", width = total.to_string().len());
    let relations = (
        item.origin_relation.as_deref(),
        item.destination_relation.as_deref(),
    );
    let plain_flow: String = clone_relation_flow_text(&item.name, relations);
    let flow: String = match relations {
        (Some(origin), Some(destination)) => format!(
            "{} {} {}",
            style.object_name(&clone_relation_display_name(origin)),
            style.muted("->"),
            style.object_name(&clone_relation_display_name(destination))
        ),
        _ => style.object_name(&plain_flow),
    };
    let plain_width: usize = plain_flow.chars().count();
    let relation_padding: String = " ".repeat(relation_width.max(plain_width) - plain_width);
    let action_padding: String =
        " ".repeat(ACTION_WIDTH.saturating_sub(item.action.chars().count()));
    let status: &str = match item.status {
        CloneStatusKind::Warning => "WARN",
        CloneStatusKind::Failed => "FAIL",
        CloneStatusKind::Success => "OK",
    };
    let duration: String = item.duration_seconds.map_or_else(String::new, |seconds| {
        format!("  {}", style.muted(&format!("{seconds:.2}s")))
    });
    format!(
        "  {}  {}{action_padding}  {flow}{relation_padding}  {}{duration}",
        style.muted(&position),
        style.accent(&item.action),
        style.status(status)
    )
}
