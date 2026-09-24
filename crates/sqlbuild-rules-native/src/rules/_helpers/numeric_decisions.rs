use crate::sql_scan::main::comment_end::comment_end;
use crate::sql_scan::main::quote_end::quote_end;
use crate::sql_scan::models::QuotePolicy;

const CANONICAL_NUMERIC_DECISIONS: [&str; 3] = ["-1", "0", "1"];

pub(crate) struct AuthoredDecision<'a> {
    pub(crate) authored_compact_sql: &'a str,
    pub(crate) comparison_sql: &'a str,
    pub(crate) equality: bool,
    pub(crate) output_name: Option<&'a str>,
    pub(crate) literal: &'a str,
}

pub(crate) fn compact_sql(sql: &str) -> String {
    let policy = QuotePolicy::RULES;
    let bytes = sql.as_bytes();
    let mut compact = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        let byte = bytes[index];
        let unclosed_end = match comment_end(bytes, index) {
            Ok(Some(end)) => {
                index = end;
                continue;
            }
            Ok(None) if policy.is_quote(byte) => {
                quote_end(bytes, index, policy).unwrap_or(bytes.len())
            }
            Ok(None) => {
                if !byte.is_ascii_whitespace() {
                    compact.push(byte.to_ascii_lowercase());
                }
                index += 1;
                continue;
            }
            Err(_) => break,
        };
        compact.extend(
            bytes[index..unclosed_end]
                .iter()
                .map(u8::to_ascii_lowercase),
        );
        index = unclosed_end;
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
