//! Replace macro call sites with their rendered SQL and report each substitution span.

use crate::macro_calls::_helpers::offsets::byte_offsets;
use crate::macro_calls::models::MacroSpliceSpan;

/// Splice `outputs` over ascending code-point `sites`; `None` when they do not fit `sql`.
pub fn splice_macro_calls(
    sql: &str,
    sites: &[(usize, usize)],
    outputs: &[String],
) -> Option<(String, Vec<MacroSpliceSpan>)> {
    if sites.len() != outputs.len() {
        return None;
    }
    let boundaries: Vec<usize> = sites
        .iter()
        .flat_map(|(start, end)| [*start, *end])
        .collect();
    if boundaries.windows(2).any(|pair| pair[0] > pair[1]) {
        return None;
    }
    let bytes = byte_offsets(sql, &boundaries)?;
    let mut rendered =
        String::with_capacity(sql.len() + outputs.iter().map(String::len).sum::<usize>());
    let mut spans = Vec::with_capacity(sites.len());
    let mut cursor_byte = 0;
    let mut output_chars = 0;
    for ((site, output), range) in sites.iter().zip(outputs).zip(bytes.as_chunks::<2>().0) {
        let literal = &sql[cursor_byte..range[0]];
        rendered.push_str(literal);
        output_chars += literal.chars().count();
        rendered.push_str(output);
        let output_len = output.chars().count();
        spans.push(MacroSpliceSpan {
            source_start: site.0,
            source_end: site.1,
            output_start: output_chars,
            output_end: output_chars + output_len,
        });
        output_chars += output_len;
        cursor_byte = range[1];
    }
    rendered.push_str(&sql[cursor_byte..]);
    Some((rendered, spans))
}
