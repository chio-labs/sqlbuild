//! Python's `inspect.cleandoc` (3.12), which SQL test and scenario bodies go through.

use crate::text::_helpers::cleandoc::{expand_tabs, skip_chars};
use crate::text::main::is_python_space::is_python_space;

/// `inspect.cleandoc(text)`: expand tabs, dedent later lines and drop outer empty lines.
pub fn python_cleandoc(text: &str) -> String {
    let expanded: String = expand_tabs(text);
    let mut lines: Vec<&str> = expanded.split('\n').collect();
    let margin: Option<usize> = lines[1..]
        .iter()
        .filter_map(|line| {
            let content = line.trim_start_matches(is_python_space);
            (!content.is_empty()).then(|| line.chars().count() - content.chars().count())
        })
        .min();
    lines[0] = lines[0].trim_start_matches(is_python_space);
    let mut cleaned: Vec<&str> = Vec::with_capacity(lines.len());
    cleaned.push(lines[0]);
    cleaned.extend(
        lines[1..]
            .iter()
            .map(|line| margin.map_or(*line, |margin| skip_chars(line, margin))),
    );
    let last: usize = cleaned
        .iter()
        .rposition(|line| !line.is_empty())
        .map_or(0, |index| index + 1);
    let first: usize = cleaned[..last]
        .iter()
        .position(|line| !line.is_empty())
        .unwrap_or(last);
    cleaned[first..last].join("\n")
}
