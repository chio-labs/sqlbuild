//! Stored rule caches decoded from their JSON form.

use std::collections::BTreeMap;

use serde_json::{Map, Value};

use crate::custom_rule_cache::constants::{ENTRIES_KEY, IDENTITY_KEY, READSETS_KEY};
use crate::custom_rule_cache::models::{StoredEntry, StoredRule};
use crate::custom_rule_cache::types::{FactKey, ReadSet};

fn strings(value: &Value) -> Option<FactKey> {
    value
        .as_array()?
        .iter()
        .map(|part| part.as_str().map(str::to_owned))
        .collect()
}

fn readset(value: &Value) -> Option<ReadSet> {
    value.as_array()?.iter().map(strings).collect()
}

fn entry(value: &Value) -> Option<StoredEntry> {
    let [subject_identity, readset, reads_digest, findings] = value.as_array()?.as_slice() else {
        return None;
    };
    Some(StoredEntry {
        subject_identity: subject_identity.as_str()?.to_owned(),
        readset: readset.as_u64()? as usize,
        reads_digest: reads_digest.as_str()?.to_owned(),
        findings: findings.as_array()?.clone(),
    })
}

pub(crate) fn stored_rule(value: &Value) -> Option<StoredRule> {
    let object: &Map<String, Value> = value.as_object()?;
    let entries: BTreeMap<String, StoredEntry> = object
        .get(ENTRIES_KEY)?
        .as_object()?
        .iter()
        .map(|(subject, value)| Some((subject.clone(), entry(value)?)))
        .collect::<Option<_>>()?;
    Some(StoredRule {
        identity: object.get(IDENTITY_KEY)?.as_str()?.to_owned(),
        readsets: object
            .get(READSETS_KEY)?
            .as_array()?
            .iter()
            .map(readset)
            .collect::<Option<_>>()?,
        entries,
    })
}
