//! The header pieces of a `--debug` console line.

use crate::cli_text::models::CliStyle;
use crate::diagnostic_routing::constants::LOGGER_PREFIX;
use crate::diagnostic_text::models::DiagnosticRecordText;

/// Whether Python's `str.isspace()` holds for `character`.
pub(crate) fn python_space(character: char) -> bool {
    character.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&character)
}

/// The message with ` SQL` lowered to ` sql`.
fn normalized_message(message: &str) -> String {
    message.replace(" SQL", " sql")
}

/// The subject, name, event, context tokens and message, when the record has a subject.
fn context_message(record: &DiagnosticRecordText, style: CliStyle) -> Option<String> {
    let subject: &String = record.subject.as_ref()?;
    let mut parts: Vec<String> = vec![subject.clone()];
    if let Some(name) = &record.name {
        parts.push(style.object_name(name));
    }
    if let Some(event) = &record.event {
        parts.push(event.clone());
    }
    for (label, value) in &record.tokens {
        parts.push(format!("{label}={value}"));
    }
    if let Some(duration_seconds) = record.duration_seconds {
        parts.push(format!("duration={duration_seconds:.2}s"));
    }
    let message: String = normalized_message(&record.message);
    if !message.is_empty() {
        parts.push(message);
    }
    Some(parts.join(" "))
}

/// The level tag and context or logger scope that open a console line.
pub(crate) fn header(record: &DiagnosticRecordText, style: CliStyle) -> String {
    let level_tag: String = format!("[{}]", record.level_name.to_lowercase());
    let context: String = context_message(record, style).unwrap_or_else(|| {
        let scope: &str = record
            .logger_name
            .strip_prefix(LOGGER_PREFIX)
            .unwrap_or(&record.logger_name);
        format!(
            "{} {}",
            style.object_name(scope),
            normalized_message(&record.message)
        )
    });
    if !style.use_color {
        return format!("{level_tag} {context}");
    }
    format!("{} {context}", style.log_label(&level_tag))
}
