//! Locate and replace the compile_timings object inside a stored JSON report.

const OPENING: &str = "\n  \"compile_timings\": {";
const CLOSING: &str = "\n  }";

/// Byte span of the top-level compile_timings object, if any.
pub(crate) fn compile_timings_span(stdout: &str) -> Option<(usize, usize)> {
    let opening: usize = stdout.find(OPENING)?;
    let start: usize = opening + OPENING.len() - 1;
    let closing: usize = start + stdout[start..].find(CLOSING)?;
    if stdout[start + 1..closing].contains('{') {
        return None;
    }
    Some((start, closing + CLOSING.len()))
}

/// Splice freshly measured timings into a stored two-space-indented JSON report.
pub(crate) fn replace_compile_timings(
    stdout: &str,
    span: (usize, usize),
    timings: &[(String, i64)],
) -> Option<String> {
    let rendered: Vec<String> = timings
        .iter()
        .map(|(name, value)| format!("    {}: {value}", json_string(name)))
        .collect();
    let head: &str = stdout.get(..span.0)?;
    let tail: &str = stdout.get(span.1..)?;
    Some(format!("{head}{{\n{}{CLOSING}{tail}", rendered.join(",\n")))
}

/// `json.dumps(name)` for a string: ASCII-escaped and double-quoted.
fn json_string(text: &str) -> String {
    let mut quoted: String = String::from("\"");
    for character in text.chars() {
        match character {
            '"' => quoted.push_str("\\\""),
            '\\' => quoted.push_str("\\\\"),
            '\n' => quoted.push_str("\\n"),
            '\r' => quoted.push_str("\\r"),
            '\t' => quoted.push_str("\\t"),
            '\u{08}' => quoted.push_str("\\b"),
            '\u{0c}' => quoted.push_str("\\f"),
            ' '..='~' => quoted.push(character),
            _ => {
                let mut units: [u16; 2] = [0; 2];
                for unit in character.encode_utf16(&mut units) {
                    quoted.push_str(&format!("\\u{unit:04x}"));
                }
            }
        }
    }
    quoted.push('"');
    quoted
}
