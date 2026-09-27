use std::collections::BTreeSet;

use crate::constants::{
    INTERMEDIATE_LAYER_DIRECTORY, MART_LAYER_DIRECTORY, MODEL_SCHEMA_CONFIG_KEY, REFERENCE_KIND,
    STAGING_LAYER_DIRECTORY,
};
use crate::models::{Fault, Model, RuleMetadata};
use crate::rules::_helpers::evaluation::parse_name;
use crate::rules::models::{FaultCollector, ProjectEvaluationRequest};

const NO_CANONICAL_LAYER_FOLDER: &str = "no canonical layer folder";

pub(crate) fn explicit_model_schema(model: &Model, rule: &RuleMetadata, faults: &FaultCollector) {
    if model
        .authored_config_keys
        .iter()
        .any(|key| key == MODEL_SCHEMA_CONFIG_KEY)
    {
        let schema = model
            .config
            .get(MODEL_SCHEMA_CONFIG_KEY)
            .and_then(serde_json::Value::as_str)
            .unwrap_or("<resolved>");
        faults.push(model_fault(
            model,
            rule,
            format!(
                "model declares schema {schema:?} explicitly; model schemas must come from path defaults"
            ),
            None,
        ));
    }
}

pub(crate) fn internal_forward_refs(
    evaluation: &ProjectEvaluationRequest<'_>,
    rule: &RuleMetadata,
    faults: &FaultCollector,
) {
    let configured: BTreeSet<(String, String)> = evaluation
        .request
        .config
        .graph_edge_exceptions
        .iter()
        .map(|entry| (entry.consumer.clone(), entry.dependency.clone()))
        .collect();
    let mut used: BTreeSet<(String, String)> = BTreeSet::new();
    for model in &evaluation.request.models {
        let Some(current) = parse_name(&model.name) else {
            continue;
        };
        let Some(current_rank) = internal_layer_order(&current.layer) else {
            continue;
        };
        for reference in &model.references {
            if reference.ref_kind != REFERENCE_KIND {
                continue;
            }
            let Some(upstream) = parse_name(&reference.ref_name) else {
                continue;
            };
            let Some(upstream_rank) = internal_layer_order(&upstream.layer) else {
                continue;
            };
            if upstream_rank <= current_rank {
                continue;
            }
            let edge = (model.name.clone(), reference.ref_name.clone());
            if configured.contains(&edge) {
                used.insert(edge);
                continue;
            }
            faults.push(model_fault(
                model,
                rule,
                format!(
                    "internal {} model {:?} depends on later internal {} model {:?}",
                    current.layer, model.name, upstream.layer, reference.ref_name
                ),
                Some("Keep the consumer in its semantic layer. Move the required logic into the same or an earlier internal layer, or expose it through an approved published mart interface. For temporary debt, configure this exact consumer/dependency edge with a reason; do not rename or move the consumer merely to satisfy this rule.".into()),
            ));
        }
    }
    for exception in configured.difference(&used) {
        faults.push(Fault {
            unevaluated: false,
            code: rule.code.clone(),
            path: "sqlbuild_project.toml".into(),
            line: 1,
            column: 1,
            message: format!(
                "graph edge exception is stale: {} -> {}",
                exception.0, exception.1
            ),
            remediation: "Remove the stale graph_edge_exceptions entry.".into(),
        });
    }
}

pub(crate) fn name_folder_alignment(model: &Model, rule: &RuleMetadata, faults: &FaultCollector) {
    let Some(parts) = parse_name(&model.name) else {
        return;
    };
    let expected = canonical_folder_for_layer(&parts.layer);
    let actual = canonical_folder_in_path(&model.relative_path);
    if actual != Some(expected) {
        faults.push(model_fault(
            model,
            rule,
            format!(
                "model {:?} declares layer {:?} but is stored under {:?}; expected canonical folder {:?}",
                model.name,
                parts.layer,
                actual.unwrap_or(NO_CANONICAL_LAYER_FOLDER),
                expected
            ),
            None,
        ));
    }
}

pub(crate) fn name_schema_alignment(model: &Model, rule: &RuleMetadata, faults: &FaultCollector) {
    let Some(parts) = parse_name(&model.name) else {
        return;
    };
    let Some(actual) = model.logical_schema.as_deref() else {
        return;
    };
    let expected = logical_schema_for_layer(&parts.layer);
    if !actual.eq_ignore_ascii_case(expected) {
        faults.push(model_fault(
            model,
            rule,
            format!(
                "model {:?} resolves to schema {:?}, but layer {:?} requires schema {:?}",
                model.name, actual, parts.layer, expected
            ),
            None,
        ));
    }
}

fn internal_layer_order(layer: &str) -> Option<usize> {
    match layer {
        "stg" | "stg_v" => Some(0),
        "int_clean" => Some(1),
        "int_v" | "int_enriched" => Some(2),
        _ => None,
    }
}

fn canonical_folder_for_layer(layer: &str) -> &'static str {
    match layer {
        "stg" | "stg_v" => STAGING_LAYER_DIRECTORY,
        "int_clean" => "intermediate/clean",
        "int_enriched" | "int_v" => "intermediate/enriched",
        _ => MART_LAYER_DIRECTORY,
    }
}

fn canonical_folder_in_path(relative_path: &str) -> Option<&'static str> {
    let parts: Vec<&str> = relative_path.split('/').collect();
    let parent = &parts[..parts.len().saturating_sub(1)];
    for (index, component) in parent.iter().enumerate().skip(1) {
        if *component == STAGING_LAYER_DIRECTORY {
            return Some(STAGING_LAYER_DIRECTORY);
        }
        if *component == MART_LAYER_DIRECTORY {
            return Some(MART_LAYER_DIRECTORY);
        }
        if *component == INTERMEDIATE_LAYER_DIRECTORY {
            return match parent.get(index + 1).copied() {
                Some("clean") => Some("intermediate/clean"),
                Some("enriched") => Some("intermediate/enriched"),
                _ => None,
            };
        }
    }
    None
}

fn logical_schema_for_layer(layer: &str) -> &'static str {
    match layer {
        "stg" | "stg_v" => STAGING_LAYER_DIRECTORY,
        "int_clean" | "int_enriched" | "int_v" => INTERMEDIATE_LAYER_DIRECTORY,
        _ => MART_LAYER_DIRECTORY,
    }
}

fn model_fault(
    model: &Model,
    rule: &RuleMetadata,
    message: String,
    remediation: Option<String>,
) -> Fault {
    Fault {
        unevaluated: false,
        code: rule.code.clone(),
        path: model.relative_path.clone(),
        line: 1,
        column: 1,
        message,
        remediation: remediation.unwrap_or_else(|| rule.remediation.clone()),
    }
}
