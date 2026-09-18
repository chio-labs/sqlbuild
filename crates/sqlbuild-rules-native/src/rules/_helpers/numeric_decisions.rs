const CANONICAL_NUMERIC_DECISIONS: [&str; 3] = ["-1", "0", "1"];

pub(crate) struct AuthoredDecision<'a> {
    pub(crate) authored_compact_sql: &'a str,
    pub(crate) comparison_sql: &'a str,
    pub(crate) equality: bool,
    pub(crate) output_name: Option<&'a str>,
    pub(crate) literal: &'a str,
}

pub(crate) fn compact_sql(sql: &str) -> String {
    let bytes = sql.as_bytes();
    let mut compact = Vec::with_capacity(bytes.len());
    let mut index = 0;
    let mut quote: Option<u8> = None;
    let mut line_comment = false;
    let mut block_comment = false;
    while index < bytes.len() {
        let byte = bytes[index];
        let next = bytes.get(index + 1).copied();
        if line_comment {
            line_comment = byte != b'\n';
            index += 1;
            continue;
        }
        if block_comment {
            if byte == b'*' && next == Some(b'/') {
                block_comment = false;
                index += 2;
            } else {
                index += 1;
            }
            continue;
        }
        if let Some(active_quote) = quote {
            compact.push(byte.to_ascii_lowercase());
            if byte == active_quote {
                if next == Some(active_quote) {
                    compact.push(active_quote);
                    index += 2;
                    continue;
                }
                quote = None;
            }
            index += 1;
            continue;
        }
        if byte == b'-' && next == Some(b'-') {
            line_comment = true;
            index += 2;
            continue;
        }
        if byte == b'/' && next == Some(b'*') {
            block_comment = true;
            index += 2;
            continue;
        }
        if matches!(byte, b'\'' | b'"') {
            quote = Some(byte);
        }
        if !byte.is_ascii_whitespace() {
            compact.push(byte.to_ascii_lowercase());
        }
        index += 1;
    }
    String::from_utf8(compact).unwrap_or_default()
}

pub(crate) fn is_authored_decision(decision: AuthoredDecision<'_>) -> bool {
    !CANONICAL_NUMERIC_DECISIONS.contains(&decision.literal)
        && decision
            .authored_compact_sql
            .contains(&compact_sql(decision.comparison_sql))
        && !decision.output_name.is_some_and(|name| {
            decision.equality && name.ends_with(&format!("_{}", decision.literal))
        })
}
