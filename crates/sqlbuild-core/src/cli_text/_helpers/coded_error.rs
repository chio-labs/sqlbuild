//! A result-stored coded error, as CLI expected errors render it.

use crate::cli_text::models::CliStyle;

/// `error[CODE]: message` or `[CODE] message`, later lines muted, then any help line.
pub(crate) fn coded_error(
    (code, message, help): (&str, &str, Option<&str>),
    include_error_label: bool,
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
        style.error_strong(&if include_error_label {
            format!("error[{code}]:")
        } else {
            format!("[{code}]")
        })
    );
    if let Some(help) = help {
        rendered = format!("{rendered}\n  {} {help}", style.muted("= help:"));
    }
    rendered
}
