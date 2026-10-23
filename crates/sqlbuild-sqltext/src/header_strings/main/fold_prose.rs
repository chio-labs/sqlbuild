//! Folded prose: the text a description stores, however its lines are wrapped.

use crate::header_strings::constants::PARAGRAPH_BREAK;

fn is_layout_space(character: char) -> bool {
    matches!(character, ' ' | '\t' | '\n' | '\r')
}

/// The line breaks in a run of layout space, counting `\r\n` once.
fn line_breaks(run: &str) -> usize {
    run.matches('\n').count() + run.matches('\r').count() - run.matches("\r\n").count()
}

/// The text `written` stores as folded prose.
///
/// Text on one line is kept exactly. Otherwise the space at either end is dropped, a line break
/// with the spaces around it is one space, and a blank line is a paragraph break (`\n\n`).
pub fn fold_prose(written: &str) -> String {
    if !written.contains(['\n', '\r']) {
        return written.to_owned();
    }
    let trimmed: &str = written.trim_matches(is_layout_space);
    let mut folded: String = String::with_capacity(trimmed.len());
    let mut rest: &str = trimmed;
    while let Some(space_start) = rest.find(is_layout_space) {
        folded.push_str(&rest[..space_start]);
        let after: &str = &rest[space_start..];
        let space_end: usize = after
            .find(|character: char| !is_layout_space(character))
            .unwrap_or(after.len());
        let run: &str = &after[..space_end];
        match line_breaks(run) {
            0 => folded.push_str(run),
            1 => folded.push(' '),
            _ => folded.push_str(PARAGRAPH_BREAK),
        }
        rest = &after[space_end..];
    }
    folded.push_str(rest);
    folded
}
