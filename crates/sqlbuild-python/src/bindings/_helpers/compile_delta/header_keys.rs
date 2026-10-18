//! Each model header's keys as digests, so a delta compile can tell which keys an edit changed.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use sqlbuild_cache::digest::main::bytes_digest::bytes_digest;
use sqlbuild_cache::digest::main::hex_digest::hex_digest;
use sqlbuild_discovery::model_files::main::parse_model_text::parse_model_text;
use sqlbuild_sqltext::compiler::models::AuthoredValue;

use crate::bindings::_helpers::compile_delta::context::{capture, capturing};
use crate::bindings::_helpers::discovery::model_records::model_file_options;

/// One model's header keys with the digest of each authored value, sorted by key.
pub(crate) type HeaderKeys = Vec<(String, String)>;

/// Header keys a delta compile recompiles the model for; any other changed key falls back.
const PATCHED_KEYS: [&str; 6] = [
    "description",
    "columns",
    "dynamic_columns",
    "model_schema",
    "audits",
    "contract",
];
/// `materialized` values a delta compile handles; others name materializations it cannot.
const PATCHED_MATERIALIZATIONS: [&str; 2] = ["view", "table"];
const MATERIALIZED_KEY: &str = "materialized";

fn header_keys(values: &[(String, AuthoredValue)]) -> HeaderKeys {
    let mut keys: HeaderKeys = values
        .iter()
        .map(|(key, value)| {
            let text: String = format!("{value:?}");
            (key.clone(), hex_digest(&bytes_digest(text.as_bytes())))
        })
        .collect();
    keys.sort();
    keys
}

/// Record one discovered model's header keys for the image.
pub(crate) fn record_header_keys(relative_path: &str, values: &[(String, AuthoredValue)]) {
    if !capturing() {
        return;
    }
    let keys: HeaderKeys = header_keys(values);
    let path: String = relative_path.replace('\\', "/");
    capture(|capture| {
        capture.header_keys.insert(path, keys);
    });
}

/// What an edit did to one model's header.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum HeaderChange {
    /// The header's keys and values are unchanged.
    Unchanged,
    /// These keys changed, every one of which the delta recompiles.
    Patched(BTreeSet<String>),
    /// Why the delta cannot recompile this header change.
    Unsupported(String),
    /// The file does not parse; the delta reports its error as a full compile would.
    Unparsed,
}

/// How the header of the model file at `path` changed against its recorded keys.
pub(crate) fn header_change(
    project_dir: &Path,
    relative_path: &str,
    stored: Option<&HeaderKeys>,
) -> HeaderChange {
    let Some(stored) = stored else {
        return HeaderChange::Unsupported(format!("{relative_path} has no recorded header"));
    };
    let Ok(contents) = std::fs::read_to_string(project_dir.join(relative_path)) else {
        return HeaderChange::Unparsed;
    };
    let file_path: String = project_dir
        .join(relative_path)
        .to_string_lossy()
        .into_owned();
    let Ok(parsed) = parse_model_text(&file_path, contents, &model_file_options()) else {
        return HeaderChange::Unparsed;
    };
    let current: HeaderKeys = header_keys(&parsed.header_values);
    let stored_map: BTreeMap<&str, &str> = stored
        .iter()
        .map(|(key, digest)| (key.as_str(), digest.as_str()))
        .collect();
    let current_map: BTreeMap<&str, &str> = current
        .iter()
        .map(|(key, digest)| (key.as_str(), digest.as_str()))
        .collect();
    let changed: BTreeSet<String> = stored_map
        .keys()
        .chain(current_map.keys())
        .filter(|key| stored_map.get(*key) != current_map.get(*key))
        .map(|key| (*key).to_owned())
        .collect();
    if changed.is_empty() {
        return HeaderChange::Unchanged;
    }
    for key in &changed {
        if key == MATERIALIZED_KEY {
            let value = parsed.header_values.iter().find(|(name, _)| name == key);
            let supported: bool = matches!(
                value,
                Some((_, AuthoredValue::BareWord(word) | AuthoredValue::String(word)))
                    if PATCHED_MATERIALIZATIONS.contains(&word.as_str())
            );
            if !supported {
                return HeaderChange::Unsupported(format!(
                    "{relative_path} changed its materialization beyond views and tables"
                ));
            }
        } else if !PATCHED_KEYS.contains(&key.as_str()) {
            return HeaderChange::Unsupported(format!(
                "{relative_path} changed its {key} header key"
            ));
        }
    }
    HeaderChange::Patched(changed)
}

/// Whether a custom rule reads a fact of this model that the changed header keys decide.
pub(crate) fn custom_rule_reads(
    fact_digests: &[(Vec<String>, String)],
    model: (&str, &str),
    changed: &BTreeSet<String>,
) -> Option<String> {
    let (path, name) = model;
    for (key, _) in fact_digests {
        let Some((fact, arguments)) = key.split_first() else {
            continue;
        };
        if !arguments
            .iter()
            .any(|argument| argument == path || argument == name)
        {
            continue;
        }
        let reads: &[&str] = match fact.as_str() {
            "contracts.enforced" | "contract" => &["contract"],
            "contracts.grain" | "grain" => &["contract", "columns"],
            "columns.declared" | "columns.names" => &["columns", "dynamic_columns"],
            "materialized" => &["materialized"],
            "tests.for_model" | "audits.for_model" => &["audits", "columns"],
            _ => &[],
        };
        if let Some(key) = reads.iter().find(|key| changed.contains(**key)) {
            return Some(format!("a custom rule reads {name}'s {key}"));
        }
    }
    None
}
