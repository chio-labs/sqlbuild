//! Bounded sections, aligned name/value rows and ANSI stripping, as `sqlbuild.presentation` does.

use crate::cli_text::constants::MIN_NAME_COLUMN_WIDTH;
use crate::cli_text::models::{CliStyle, DisplayLimit};

/// The text without ANSI SGR sequences (`ESC [ digits-and-semicolons m`).
pub(crate) fn strip_ansi(text: &str) -> String {
    let mut stripped: String = String::with_capacity(text.len());
    let mut rest: &str = text;
    while let Some(start) = rest.find("\x1b[") {
        stripped.push_str(&rest[..start]);
        let after: &str = &rest[start + 2..];
        let parameters: usize = after
            .find(|character: char| !(character.is_ascii_digit() || character == ';'))
            .unwrap_or(after.len());
        if after[parameters..].starts_with('m') {
            rest = &after[parameters + 1..];
        } else {
            stripped.push('\x1b');
            rest = &rest[start + 1..];
        }
    }
    stripped.push_str(rest);
    stripped
}

/// `count_header_style` over `plan_section`: `Title (count)` as a bold title and dim count.
pub(crate) fn section_header(style: CliStyle, text: &str) -> String {
    if let Some(split) = text.rfind(" (")
        && text.ends_with(')')
    {
        return format!(
            "{} {}",
            style.plan_section(&text[..split]),
            style.muted(&text[split + 1..])
        );
    }
    style.plan_section(text)
}

/// How many of `total` entries a section shows.
pub(crate) fn visible_count(total: usize, display: &DisplayLimit) -> usize {
    display.max_entries.map_or(total, |limit| total.min(limit))
}

/// The dim `... and N more` line when a section hides entries.
pub(crate) fn overflow_line(
    (total, visible): (usize, usize),
    indent: &str,
    display: &DisplayLimit,
) -> Option<String> {
    (total > visible).then(|| {
        CliStyle { use_color: true }.muted(&format!(
            "{indent}... and {} more (use {} to show all)",
            total - visible,
            display.overflow_flag
        ))
    })
}

/// The widest name, but at least the minimum name column.
pub(crate) fn name_column_width<'a>(names: impl Iterator<Item = &'a str>) -> usize {
    names
        .map(|name| name.chars().count())
        .max()
        .unwrap_or(0)
        .max(MIN_NAME_COLUMN_WIDTH)
}

/// `  name<padding> value`, with the value dim unless `dim_value` is off.
pub(crate) fn name_value_line(name: &str, value: &str, width: usize, dim_value: bool) -> String {
    let style: CliStyle = CliStyle { use_color: true };
    let rendered: String = if dim_value {
        style.muted(value)
    } else {
        value.to_owned()
    };
    let padding: String = " ".repeat(width.saturating_sub(name.chars().count()));
    format!("  {}{padding} {rendered}", style.object_name(name))
}

/// A comma-separated name list cut to the section limit with a `+N more` note.
pub(crate) fn capped_names(
    names: &[String],
    display: &DisplayLimit,
    name_style: impl Fn(&str) -> String,
) -> String {
    let visible: usize = visible_count(names.len(), display);
    let base: String = names[..visible]
        .iter()
        .map(|name| name_style(name))
        .collect::<Vec<String>>()
        .join(", ");
    if visible >= names.len() {
        return base;
    }
    format!(
        "{base}, ... (+{} more; use {} to show all)",
        names.len() - visible,
        display.overflow_flag
    )
}
