//! Host response decoding.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Map, Value};

use crate::custom_host_pool::_helpers::payload_values::{fact_key, python_text, readset};
use crate::custom_host_pool::constants::{
    CUSTOM_RULE_PROJECT_SUBJECT, INVALID_EVALUATION, INVALID_FINDINGS, INVALID_PAYLOAD,
};
use crate::custom_host_pool::models::{HostEvaluation, HostSlice};
use crate::custom_host_pool::types::FactKey;

/// The slice a host response describes, or the `RulesError` message of a malformed one.
pub(crate) fn decoded_slice(response: &Value) -> Result<HostSlice, String> {
    let Value::Object(payload) = response else {
        return Err(INVALID_PAYLOAD.to_owned());
    };
    let (
        Some(Value::Array(raw_readsets)),
        Some(Value::Array(raw_evaluations)),
        Some(Value::Object(raw_untracked)),
        Some(Value::Array(raw_uncacheable)),
        Some(Value::Array(raw_observed)),
    ) = (
        payload.get("readsets"),
        payload.get("evaluations"),
        payload.get("untracked"),
        payload.get("uncacheable"),
        payload.get("observed"),
    )
    else {
        return Err(INVALID_PAYLOAD.to_owned());
    };
    let readsets: Vec<Vec<FactKey>> = raw_readsets.iter().map(readset).collect();
    let untracked_reads: BTreeMap<String, Vec<FactKey>> = raw_untracked
        .iter()
        .map(|(code, reads)| (code.clone(), readset(reads)))
        .collect();
    let evaluations: Vec<HostEvaluation> = raw_evaluations
        .iter()
        .map(|item| evaluation(item, &readsets, &untracked_reads))
        .collect::<Result<_, String>>()?;
    Ok(HostSlice {
        evaluations,
        uncacheable: raw_uncacheable.iter().map(python_text).collect(),
        observed: observed(raw_observed),
        bounded: payload.get("bounded") == Some(&Value::Bool(true)),
        stateful: match payload.get("stateful") {
            Some(Value::Array(codes)) => codes.iter().map(python_text).collect(),
            Some(_) | None => BTreeSet::new(),
        },
        untracked_reads,
    })
}

fn evaluation(
    item: &Value,
    readsets: &[Vec<FactKey>],
    untracked: &BTreeMap<String, Vec<FactKey>>,
) -> Result<HostEvaluation, String> {
    let Value::Object(item) = item else {
        return Err(INVALID_EVALUATION.to_owned());
    };
    let code: String = item
        .get("code")
        .map(python_text)
        .ok_or(INVALID_EVALUATION)?;
    let Some(Value::Array(findings)) = item.get("findings") else {
        return Err(INVALID_FINDINGS.to_owned());
    };
    let reads: Option<Vec<FactKey>> = match item.get("reads") {
        Some(Value::Number(index)) if !untracked.contains_key(&code) => match index.as_u64() {
            Some(index) => usize::try_from(index)
                .map_or(None, |index| readsets.get(index))
                .cloned(),
            None => None,
        },
        Some(_) | None => None,
    };
    Ok(HostEvaluation {
        subject: match item.get("subject") {
            None | Some(Value::Null) => CUSTOM_RULE_PROJECT_SUBJECT.to_owned(),
            Some(subject) => python_text(subject),
        },
        findings: findings.iter().map(finding).collect(),
        reads,
        code,
    })
}

fn finding(value: &Value) -> Value {
    match value {
        Value::Object(fields) => Value::Object(fields.clone()),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) | Value::Array(_) => {
            Value::Object(Map::new())
        }
    }
}

fn observed(raw: &[Value]) -> BTreeMap<FactKey, Option<String>> {
    let mut observed: BTreeMap<FactKey, Option<String>> = BTreeMap::new();
    for entry in raw {
        if let Value::Array(pair) = entry
            && let [key, digest] = pair.as_slice()
        {
            let digest: Option<String> = match digest {
                Value::Null => None,
                Value::Bool(_)
                | Value::Number(_)
                | Value::String(_)
                | Value::Array(_)
                | Value::Object(_) => Some(python_text(digest)),
            };
            observed.insert(fact_key(key), digest);
        }
    }
    observed
}
