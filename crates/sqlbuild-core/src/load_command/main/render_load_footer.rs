//! The final load summary: loader warnings, then the completion line.

use crate::cli_text::main::format_completion_line::format_completion_line;
use crate::cli_text::main::format_summary_footer::format_summary_footer;
use crate::cli_text::models::{CliStyle, CompletionState, SummaryCount};
use crate::load_command::models::{LoadCounts, LoadResultText};

fn summary_count(label: &str, value: i64) -> SummaryCount {
    SummaryCount {
        label: label.to_owned(),
        value,
    }
}

/// Warnings by source when any, a blank line, and the completion line with counts and elapsed time.
#[must_use]
pub fn render_load_footer(
    results: &[LoadResultText],
    (counts, elapsed_seconds): (LoadCounts, f64),
    style: CliStyle,
) -> String {
    let mut text: String = String::new();
    for result in results
        .iter()
        .filter(|result| !result.warning_messages.is_empty())
    {
        if text.is_empty() {
            text.push_str(&format!("\n{}\n\n", style.warning_strong("Warnings:")));
        }
        text.push_str(&format!(
            "  {}  (loader {})\n",
            result.source_name, result.loader_name
        ));
        for message in &result.warning_messages {
            text.push_str(&format!("    {message}\n"));
        }
    }
    let footer: String = format_summary_footer(
        style,
        &[
            summary_count("PASS", counts.pass),
            summary_count("WARN", counts.warn),
            summary_count("FAIL", counts.fail),
            summary_count("SKIP", counts.skip),
            summary_count("TOTAL", counts.total),
        ],
        Some(&format!("{elapsed_seconds:.2}s")),
    );
    let (state, label) = if counts.fail != 0 {
        (CompletionState::Fail, "Completed with errors")
    } else if counts.warn != 0 {
        (CompletionState::Warn, "Completed with warnings")
    } else {
        (CompletionState::Ok, "Completed successfully")
    };
    format!(
        "{text}\n{}\n",
        format_completion_line(style, state, label, Some(&footer))
    )
}
