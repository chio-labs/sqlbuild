//! `selected_sql_codes`: the built-in SQL rule codes a `select`/`ignore` pair enables.

use crate::constants::SQL_RULE_PREFIX;
use crate::rules::main::catalogue::catalogue;

fn matches_any(code: &str, selectors: &[String]) -> bool {
    for selector in selectors {
        if code.starts_with(selector.as_str()) {
            return true;
        }
    }
    false
}

/// Catalogue SQL rule codes matching a `select` prefix and no `ignore` prefix, in catalogue order.
#[must_use]
pub fn selected_sql_codes(select: &[String], ignore: &[String]) -> Vec<String> {
    let mut codes: Vec<String> = Vec::new();
    for rule in catalogue() {
        let code: String = rule.code;
        if code.starts_with(SQL_RULE_PREFIX)
            && matches_any(&code, select)
            && !matches_any(&code, ignore)
        {
            codes.push(code);
        }
    }
    codes
}
