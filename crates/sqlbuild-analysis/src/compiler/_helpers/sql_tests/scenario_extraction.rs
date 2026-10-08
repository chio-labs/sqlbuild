//! Python's `extract_sql_scenario_ctes` for scenarios its top-level scanner reads exactly.

use serde::Serialize;

use crate::compiler::_helpers::sql_tests::extraction::{
    Cte, extract_ctes_with_quoting, validate_independence,
};

/// Characters whose Python case mapping reaches ASCII, which Python's keyword match would accept.
const CASE_MAPPED_TO_ASCII: [char; 20] = [
    '\u{df}', '\u{130}', '\u{131}', '\u{149}', '\u{17f}', '\u{1f0}', '\u{1e96}', '\u{1e97}',
    '\u{1e98}', '\u{1e99}', '\u{1e9a}', '\u{1e9e}', '\u{212a}', '\u{fb00}', '\u{fb01}', '\u{fb02}',
    '\u{fb03}', '\u{fb04}', '\u{fb05}', '\u{fb06}',
];

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct ClassifiedScenario {
    authored: Vec<Cte>,
    expected: Vec<Cte>,
    assertions: Vec<Cte>,
    source_fixtures: Vec<String>,
    ref_fixtures: Vec<String>,
    seed_fixtures: Vec<String>,
    dbt_ref_fixtures: Vec<String>,
    expected_models: Vec<String>,
    assertion_names: Vec<String>,
}

pub(crate) fn extract_scenario_json(sql: &str, file: &str) -> Result<Option<String>, String> {
    if sql.chars().any(|character| {
        matches!(character, '\u{1c}'..='\u{1f}') || CASE_MAPPED_TO_ASCII.contains(&character)
    }) {
        return Ok(None);
    }
    let Ok((ctes, quoted)) = extract_ctes_with_quoting(sql, file) else {
        return Ok(None);
    };
    if quoted || !ctes.iter().all(|cte| is_plain_identifier(&cte.0)) {
        return Ok(None);
    }
    if validate_independence(&ctes, file).is_err() {
        return Ok(None);
    }
    let Some(scenario) = classify(ctes) else {
        return Ok(None);
    };
    serde_json::to_string(&scenario)
        .map(Some)
        .map_err(|error| error.to_string())
}

/// Python's `_read_identifier` reads only `[A-Za-z_][A-Za-z0-9_]*` the same way.
fn is_plain_identifier(name: &str) -> bool {
    let mut bytes = name.bytes();
    bytes
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == b'_')
        && bytes.all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
}

fn classify(ctes: Vec<Cte>) -> Option<ClassifiedScenario> {
    let mut scenario: ClassifiedScenario = ClassifiedScenario::default();
    for cte in ctes {
        let name: String = cte.0.clone();
        if let Some(value) = name.strip_prefix("__source__") {
            scenario.source_fixtures.push(required(value)?);
            scenario.authored.push(cte);
        } else if let Some(value) = name.strip_prefix("__ref__") {
            scenario.ref_fixtures.push(required(value)?);
            scenario.authored.push(cte);
        } else if let Some(value) = name.strip_prefix("__seed__") {
            scenario.seed_fixtures.push(required(value)?);
            scenario.authored.push(cte);
        } else if let Some(value) = name.strip_prefix("__dbt_ref__") {
            scenario.dbt_ref_fixtures.push(required(value)?);
            scenario.authored.push(cte);
        } else if let Some(value) = name.strip_prefix("__expected__") {
            scenario.expected_models.push(required(value)?);
            scenario.expected.push(cte);
        } else if let Some(value) = name.strip_prefix("__assert__") {
            scenario.assertion_names.push(required(value)?);
            scenario.assertions.push(cte);
        } else if name.starts_with("__macro__") {
            return None;
        } else {
            scenario.authored.push(cte);
        }
    }
    let has_fixture: bool = !(scenario.source_fixtures.is_empty()
        && scenario.ref_fixtures.is_empty()
        && scenario.seed_fixtures.is_empty()
        && scenario.dbt_ref_fixtures.is_empty());
    let has_check: bool =
        !(scenario.expected_models.is_empty() && scenario.assertion_names.is_empty());
    (has_fixture && has_check).then_some(scenario)
}

fn required(value: &str) -> Option<String> {
    (!value.is_empty()).then(|| value.to_owned())
}
