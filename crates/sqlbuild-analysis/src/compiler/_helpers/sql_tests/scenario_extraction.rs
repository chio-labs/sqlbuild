//! `extract_sql_scenario_ctes`: the top-level scan, the independence check, then classification.

use serde::Serialize;
use sqlbuild_scopes::relationship_names::main::top_level_ctes::scan_top_level_ctes;
use sqlbuild_scopes::relationship_names::models::{RelationshipSource, TopLevelCtes};
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiler::_helpers::sql_tests::check_independence::{
    IndependenceCheck, independence_error,
};

type Cte = (String, String);

const SOURCE_PREFIX: &str = "__source__";
const REF_PREFIX: &str = "__ref__";
const SEED_PREFIX: &str = "__seed__";
const DBT_REF_PREFIX: &str = "__dbt_ref__";
const EXPECTED_PREFIX: &str = "__expected__";
const ASSERT_PREFIX: &str = "__assert__";
const MACRO_PREFIX: &str = "__macro__";
const SCENARIO_CONTEXT: &str = "SQL scenario";

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

/// One scenario's error, or its classification.
#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct ScenarioOutcome {
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    scenario: Option<ClassifiedScenario>,
}

/// The scenario's classification or error, as JSON; independence errors come first.
pub(crate) fn extract_scenario_json(
    sql: &str,
    file: &str,
    syntax: &LexicalSyntax,
) -> Result<String, String> {
    let outcome: ScenarioOutcome =
        match scan_top_level_ctes(sql, file, RelationshipSource::Scenario, syntax) {
            TopLevelCtes::Failed(message) => ScenarioOutcome {
                error: Some(message),
                ..ScenarioOutcome::default()
            },
            TopLevelCtes::Scanned(ctes) => {
                let independence: Option<String> = independence_error(
                    &IndependenceCheck {
                        ctes: &ctes,
                        expected_prefix: EXPECTED_PREFIX,
                        assertion_prefix: ASSERT_PREFIX,
                        file_label: file,
                        context_label: SCENARIO_CONTEXT,
                    },
                    syntax,
                );
                match independence.map_or_else(|| classify(ctes, file), Err) {
                    Ok(scenario) => ScenarioOutcome {
                        scenario: Some(scenario),
                        ..ScenarioOutcome::default()
                    },
                    Err(message) => ScenarioOutcome {
                        error: Some(message),
                        ..ScenarioOutcome::default()
                    },
                }
            }
        };
    serde_json::to_string(&outcome).map_err(|error| error.to_string())
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
