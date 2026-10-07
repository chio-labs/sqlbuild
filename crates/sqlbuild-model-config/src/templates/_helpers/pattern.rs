//! Python's `\$\{([^{}]+)\}` matches, found left to right without overlap.

/// Return the byte spans of every template match, including the `${` and `}`.
pub(crate) fn template_spans(text: &str) -> Vec<(usize, usize)> {
    let bytes = text.as_bytes();
    let mut spans: Vec<(usize, usize)> = Vec::new();
    let mut index = 0;
    while index + 1 < bytes.len() {
        if bytes[index] == b'$' && bytes[index + 1] == b'{' {
            let body = index + 2;
            let close = bytes[body..]
                .iter()
                .position(|byte| matches!(byte, b'{' | b'}'))
                .map(|offset| body + offset);
            if let Some(close) = close
                && close > body
                && bytes[close] == b'}'
            {
                spans.push((index, close + 1));
                index = close + 1;
                continue;
            }
        }
        index += 1;
    }
    spans
}
