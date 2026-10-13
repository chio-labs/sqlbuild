//! A result-stored coded error, as CLI expected errors render it.

use crate::cli_text::models::CliStyle;

/// `[CODE] message`, later message lines muted, then the help line when there is one.
pub(crate) fn coded_error(
    (code, message, help): (&str, &str, Option<&str>),
    style: CliStyle,
) -> String {
    let mut lines = message.split('\n');
    let first: &str = lines.next().unwrap_or("");
    let rest: Vec<String> = lines.map(|line| style.muted(line)).collect();
    let rendered_message: String = if rest.is_empty() {
        message.to_owned()
    } else {
        format!("{first}\n{}", rest.join("\n"))
    };
    let mut rendered: String = format!(
        "{} {rendered_message}",
        style.error_strong(&format!("[{code}]"))
    );
    if let Some(help) = help {
        rendered = format!("{rendered}\n  {} {help}", style.muted("= help:"));
    }
    rendered
}
