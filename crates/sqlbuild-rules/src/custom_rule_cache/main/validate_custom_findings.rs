//! `validate_custom_findings`: reject findings for other rules or unrelated model paths.

use std::collections::BTreeSet;

use serde_json::Value;

use crate::custom_rule_cache::constants::{CODE_KEY, MODEL_SUBJECT_NAME, PATH_KEY};
use crate::custom_rule_cache::errors::CustomFindingError;
use crate::custom_rule_cache::models::{CustomEvaluation, CustomRule, SubjectsInput};

fn shown(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(text)) => text.clone(),
        Some(other) => other.to_string(),
        None => "None".to_owned(),
    }
}

/// An error for the first finding of an unselected rule or, for model rules, an unknown path.
pub fn validate_custom_findings(
    rules: &[CustomRule],
    project: &SubjectsInput,
    evaluations: &[CustomEvaluation],
) -> Result<(), CustomFindingError> {
    let codes: BTreeSet<&str> = rules.iter().map(|rule| rule.code.as_str()).collect();
    let model_rules: BTreeSet<&str> = rules
        .iter()
        .filter(|rule| rule.subject.as_deref() == Some(MODEL_SUBJECT_NAME))
        .map(|rule| rule.code.as_str())
        .collect();
    let paths: BTreeSet<&str> = project
        .models
        .iter()
        .map(|model| model.path.as_str())
        .collect();
    for evaluation in evaluations {
        for finding in &evaluation.findings {
            let code: Option<&Value> = finding.get(CODE_KEY);
            if !code
                .and_then(Value::as_str)
                .is_some_and(|code| codes.contains(code))
            {
                return Err(CustomFindingError(format!(
                    "custom rule host returned a finding for unselected rule {}",
                    shown(code)
                )));
            }
            let path: Option<&Value> = finding.get(PATH_KEY);
            let known: bool = path
                .and_then(Value::as_str)
                .is_some_and(|path| paths.contains(path));
            if model_rules.contains(evaluation.code.as_str()) && !known {
                return Err(CustomFindingError(format!(
                    "model-subject custom rule returned a finding for unrelated path {}",
                    shown(path)
                )));
            }
        }
    }
    Ok(())
}
