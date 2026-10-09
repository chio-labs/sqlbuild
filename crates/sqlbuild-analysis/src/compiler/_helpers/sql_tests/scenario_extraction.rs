//! Python's `extract_sql_scenario_ctes`: the exact top-level scan, then classification and errors.

use std::collections::{HashMap, HashSet};

use serde::Serialize;
use sqlbuild_scopes::relationship_names::main::top_level_ctes::scan_top_level_ctes;
use sqlbuild_scopes::relationship_names::models::{RelationshipSource, TopLevelCtes};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

type Cte = (String, String);

const SOURCE_PREFIX: &str = "__source__";
const REF_PREFIX: &str = "__ref__";
const SEED_PREFIX: &str = "__seed__";
const DBT_REF_PREFIX: &str = "__dbt_ref__";
const EXPECTED_PREFIX: &str = "__expected__";
const ASSERT_PREFIX: &str = "__assert__";
const MACRO_PREFIX: &str = "__macro__";

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

/// One scenario's error, or its classification after any Polyglot independence check.
#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct ScenarioOutcome {
    #[serde(skip_serializing_if = "Option::is_none")]
    independence: Option<Vec<Cte>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    scenario: Option<ClassifiedScenario>,
}

pub(crate) fn extract_scenario_json(
    sql: &str,
    file: &str,
    syntax: &LexicalSyntax,
) -> Result<Option<String>, String> {
    let outcome: ScenarioOutcome =
        match scan_top_level_ctes(sql, file, RelationshipSource::Scenario, syntax) {
            TopLevelCtes::Deferred => return Ok(None),
            TopLevelCtes::Failed(message) => ScenarioOutcome {
                error: Some(message),
                ..ScenarioOutcome::default()
            },
            TopLevelCtes::Scanned(ctes) => {
                let independence: Option<Vec<Cte>> =
                    python_checks_independence(&ctes).then(|| ctes.clone());
                match classify(ctes, file) {
                    Ok(scenario) => ScenarioOutcome {
                        independence,
                        scenario: Some(scenario),
                        ..ScenarioOutcome::default()
                    },
                    Err(message) => ScenarioOutcome {
                        independence,
                        error: Some(message),
                        ..ScenarioOutcome::default()
                    },
                }
            }
        };
    serde_json::to_string(&outcome)
        .map(Some)
        .map_err(|error| error.to_string())
}

/// Whether Python's independence check parses a body; when it does not, the check passes.
fn python_checks_independence(ctes: &[Cte]) -> bool {
    let mut names_by_key: HashMap<String, &str> = HashMap::new();
    for (name, _) in ctes {
        names_by_key.insert(name.to_ascii_lowercase(), name);
    }
    let keys_with_prefix = |prefix: &str| -> HashSet<&String> {
        names_by_key
            .iter()
            .filter(|(_, name)| name.starts_with(prefix))
            .map(|(key, _)| key)
            .collect()
    };
    let expected: HashSet<&String> = keys_with_prefix(EXPECTED_PREFIX);
    let assertions: HashSet<&String> = keys_with_prefix(ASSERT_PREFIX);
    for (name, body) in ctes {
        let key: String = name.to_ascii_lowercase();
        let prohibited: &str = if expected.contains(&key) {
            ASSERT_PREFIX
        } else if assertions.contains(&key) {
            EXPECTED_PREFIX
        } else {
            continue;
        };
        if folded_body_may_contain(body, prohibited) {
            return true;
        }
    }
    if expected.is_empty() || assertions.is_empty() {
        return false;
    }
    for (_, body) in ctes {
        for key in names_by_key.keys() {
            if folded_body_may_contain(body, key) {
                return true;
            }
        }
    }
    false
}

/// Whether the body's Python `casefold` may contain the text; non-ASCII may fold onto ASCII.
fn folded_body_may_contain(body: &str, lower_ascii: &str) -> bool {
    !body.is_ascii() || body.to_ascii_lowercase().contains(lower_ascii)
}

fn classify(ctes: Vec<Cte>, file: &str) -> Result<ClassifiedScenario, String> {
    let mut scenario: ClassifiedScenario = ClassifiedScenario::default();
    for cte in ctes {
        let name: &str = &cte.0;
        if let Some(value) = name.strip_prefix(SOURCE_PREFIX) {
            scenario
                .source_fixtures
                .push(required(value, "__source__<source>", file)?);
            scenario.authored.push(cte);
        } else if let Some(value) = name.strip_prefix(REF_PREFIX) {
            scenario
                .ref_fixtures
                .push(required(value, "__ref__<model>", file)?);
            scenario.authored.push(cte);
        } else if let Some(value) = name.strip_prefix(SEED_PREFIX) {
            scenario
                .seed_fixtures
                .push(required(value, "__seed__<seed>", file)?);
            scenario.authored.push(cte);
        } else if let Some(value) = name.strip_prefix(DBT_REF_PREFIX) {
            scenario.dbt_ref_fixtures.push(required(
                value,
                "__dbt_ref__<model> or __dbt_ref__<package>__<model>",
                file,
            )?);
            scenario.authored.push(cte);
        } else if let Some(value) = name.strip_prefix(EXPECTED_PREFIX) {
            scenario
                .expected_models
                .push(required(value, "__expected__<model>", file)?);
            scenario.expected.push(cte);
        } else if let Some(value) = name.strip_prefix(ASSERT_PREFIX) {
            scenario
                .assertion_names
                .push(required(value, "__assert__<assertion>", file)?);
            scenario.assertions.push(cte);
        } else if name.starts_with(MACRO_PREFIX) {
            return Err(format!(
                "SQL scenario '{file}' does not support macro mock CTE '{name}'. Scenarios run \
                 real project macros; use SQL unit tests for macro mocks."
            ));
        } else {
            scenario.authored.push(cte);
        }
    }
    if scenario.source_fixtures.is_empty()
        && scenario.ref_fixtures.is_empty()
        && scenario.seed_fixtures.is_empty()
        && scenario.dbt_ref_fixtures.is_empty()
    {
        return Err(format!(
            "SQL scenario '{file}' must define at least one __source__*, __ref__*, __seed__*, or \
             __dbt_ref__* fixture CTE"
        ));
    }
    if scenario.expected_models.is_empty() && scenario.assertion_names.is_empty() {
        return Err(format!(
            "SQL scenario '{file}' must define at least one __expected__<model> or \
             __assert__<assertion> CTE"
        ));
    }
    Ok(scenario)
}

fn required(value: &str, label: &str, file: &str) -> Result<String, String> {
    if value.is_empty() {
        return Err(format!(
            "SQL scenario '{file}' must use {label} to identify a target"
        ));
    }
    Ok(value.to_owned())
}
