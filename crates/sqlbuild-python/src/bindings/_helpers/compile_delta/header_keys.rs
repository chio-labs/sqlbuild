//! Each model header's keys as digests, so a delta compile can tell which keys an edit changed.

use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use sqlbuild_cache::digest::main::bytes_digest::bytes_digest;
use sqlbuild_discovery::model_files::main::parse_model_text::parse_model_text;
use sqlbuild_sqltext::compiler::models::AuthoredValue;
use sqlbuild_sqltext::sql_references::main::extract_sql_references::extract_sql_references;
use sqlbuild_sqltext::sql_references::models::ReferenceExtraction;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

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

/// Bytes of a digest kept per header value; a collision would need 2^64 work to find.
const KEPT_DIGEST_BYTES: usize = 16;
const HEX: &[u8; 16] = b"0123456789abcdef";

/// Append an unambiguous encoding of `value`: a tag byte, then length-prefixed parts.
fn encode_value(value: &AuthoredValue, out: &mut Vec<u8>) {
    let text = |tag: u8, text: &str, out: &mut Vec<u8>| {
        out.push(tag);
        out.extend_from_slice(&(text.len() as u64).to_le_bytes());
        out.extend_from_slice(text.as_bytes());
    };
    let list = |tag: u8, items: &[AuthoredValue], out: &mut Vec<u8>| {
        out.push(tag);
        out.extend_from_slice(&(items.len() as u64).to_le_bytes());
        for item in items {
            encode_value(item, out);
        }
    };
    let pairs = |tag: u8, items: &[(String, AuthoredValue)], out: &mut Vec<u8>| {
        out.push(tag);
        out.extend_from_slice(&(items.len() as u64).to_le_bytes());
        for (key, item) in items {
            text(b'k', key, out);
            encode_value(item, out);
        }
    };
    match value {
        AuthoredValue::Null => out.push(b'n'),
        AuthoredValue::Boolean(flag) => out.extend_from_slice(&[b'b', u8::from(*flag)]),
        AuthoredValue::BareWord(word) => text(b'w', word, out),
        AuthoredValue::String(string) => text(b's', string, out),
        AuthoredValue::List(items) => list(b'l', items, out),
        AuthoredValue::Map(items) => pairs(b'm', items, out),
        AuthoredValue::Set(items) => list(b'e', items, out),
        AuthoredValue::Tuple(items) => list(b't', items, out),
        AuthoredValue::TypedConstant(items) => pairs(b'c', items, out),
        AuthoredValue::InlineSqlHook(sql) => text(b'i', sql, out),
        AuthoredValue::NamedSqlHook(name, items) => {
            text(b'h', name, out);
            pairs(b'a', items, out);
        }
        AuthoredValue::PythonHook(name, items) => {
            text(b'p', name, out);
            pairs(b'a', items, out);
        }
    }
}

/// The pseudo header key holding a digest of the references a model's authored query names.
const REFERENCES_KEY: &str = "\u{0}references";

/// A digest of the reference calls `query_sql` names, scanned with plain `--` comments. An edit
/// that changes them changes what the model reads, which a delta compile does not patch.
fn references_digest(query_sql: &str) -> String {
    let syntax: LexicalSyntax = LexicalSyntax {
        line_comment_prefixes: vec![LINE_COMMENT.to_owned()],
        ..LexicalSyntax::default()
    };
    let mut buffer: Vec<u8> = Vec::new();
    match extract_sql_references(query_sql, &syntax) {
        ReferenceExtraction::Extracted(scan) => {
            for reference in &scan.references {
                for part in [
                    reference.kind,
                    &reference.name,
                    reference.package.as_deref().unwrap_or(""),
                ] {
                    buffer.extend_from_slice(&(part.len() as u64).to_le_bytes());
                    buffer.extend_from_slice(part.as_bytes());
                }
            }
        }
        ReferenceExtraction::Failed(_) => buffer.push(0xff),
    }
    short_hex(&bytes_digest(&buffer))
}

const LINE_COMMENT: &str = "--";

fn short_hex(digest: &[u8]) -> String {
    let mut hex: String = String::with_capacity(KEPT_DIGEST_BYTES * 2);
    for byte in &digest[..KEPT_DIGEST_BYTES] {
        hex.push(char::from(HEX[usize::from(byte >> 4)]));
        hex.push(char::from(HEX[usize::from(byte & 0x0f)]));
    }
    hex
}

fn header_keys(values: &[(String, AuthoredValue)], query_sql: &str) -> HeaderKeys {
    let mut buffer: Vec<u8> = Vec::new();
    let mut keys: HeaderKeys = values
        .iter()
        .map(|(key, value)| {
            buffer.clear();
            encode_value(value, &mut buffer);
            let hex: String = short_hex(&bytes_digest(&buffer));
            (key.clone(), hex)
        })
        .collect();
    keys.push((REFERENCES_KEY.to_owned(), references_digest(query_sql)));
    keys.sort();
    keys
}

/// Record one discovered model's header keys for the image.
pub(crate) fn record_header_keys(
    relative_path: &str,
    values: &[(String, AuthoredValue)],
    query_sql: &str,
) {
    if !capturing() {
        return;
    }
    let keys: HeaderKeys = header_keys(values, query_sql);
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
    let current: HeaderKeys = header_keys(&parsed.header_values, &parsed.query_sql);
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
    if changed.contains(REFERENCES_KEY) {
        return HeaderChange::Unsupported(format!("{relative_path} changed what it references"));
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
