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
/// Plain `--` comments, which every adapter's SQL reads as comments.
const LINE_COMMENT: &str = "--";
/// Reference call kinds and the upstream kinds they resolve to.
const REF_CALL: &str = "ref";
const SOURCE_CALL: &str = "source";
const SEED_CALL: &str = "seed";
const MODEL_KIND: &str = "model";
const SOURCE_KIND: &str = "source";
const SEED_KIND: &str = "seed";

/// Bytes of a digest kept per header value; a collision would need 2^64 work to find.
const KEPT_DIGEST_BYTES: usize = 16;
const HEX: &[u8; 16] = b"0123456789abcdef";

/// An unambiguous encoding of header values: a tag byte, then length-prefixed parts.
#[derive(Default)]
struct ValueEncoding {
    bytes: Vec<u8>,
}

impl ValueEncoding {
    fn text(&mut self, tag: u8, text: &str) {
        self.bytes.push(tag);
        self.bytes
            .extend_from_slice(&(text.len() as u64).to_le_bytes());
        self.bytes.extend_from_slice(text.as_bytes());
    }

    fn list(&mut self, tag: u8, items: &[AuthoredValue]) {
        self.bytes.push(tag);
        self.bytes
            .extend_from_slice(&(items.len() as u64).to_le_bytes());
        for item in items {
            self.value(item);
        }
    }

    fn pairs(&mut self, tag: u8, items: &[(String, AuthoredValue)]) {
        self.bytes.push(tag);
        self.bytes
            .extend_from_slice(&(items.len() as u64).to_le_bytes());
        for (key, item) in items {
            self.text(b'k', key);
            self.value(item);
        }
    }

    fn value(&mut self, value: &AuthoredValue) {
        match value {
            AuthoredValue::Null => self.bytes.push(b'n'),
            AuthoredValue::Boolean(flag) => self.bytes.extend_from_slice(&[b'b', u8::from(*flag)]),
            AuthoredValue::BareWord(word) => self.text(b'w', word),
            AuthoredValue::String(string) => self.text(b's', string),
            AuthoredValue::List(items) => self.list(b'l', items),
            AuthoredValue::Map(items) => self.pairs(b'm', items),
            AuthoredValue::Set(items) => self.list(b'e', items),
            AuthoredValue::Tuple(items) => self.list(b't', items),
            AuthoredValue::TypedConstant(items) => self.pairs(b'c', items),
            AuthoredValue::InlineSqlHook(sql) => self.text(b'i', sql),
            AuthoredValue::NamedSqlHook(name, items) => {
                self.text(b'h', name);
                self.pairs(b'a', items);
            }
            AuthoredValue::PythonHook(name, items) => {
                self.text(b'p', name);
                self.pairs(b'a', items);
            }
        }
    }
}

/// Whether every model, source and seed `query_sql` names was among the stored `upstream`.
fn references_read(query_sql: &str, upstream: &[(String, String)]) -> bool {
    let syntax: LexicalSyntax = LexicalSyntax {
        line_comment_prefixes: vec![LINE_COMMENT.to_owned()],
        ..LexicalSyntax::default()
    };
    let ReferenceExtraction::Extracted(scan) = extract_sql_references(query_sql, &syntax) else {
        return false;
    };
    scan.references.iter().all(|reference| {
        let kind: Option<&str> = match reference.kind {
            REF_CALL => Some(MODEL_KIND),
            SOURCE_CALL => Some(SOURCE_KIND),
            SEED_CALL => Some(SEED_KIND),
            _ => None,
        };
        match (kind, &reference.package) {
            (Some(kind), None) => stored_upstream(upstream, kind, &reference.name),
            _ => true,
        }
    })
}

/// Whether `upstream` holds the `kind` resource `name`.
fn stored_upstream(upstream: &[(String, String)], kind: &str, name: &str) -> bool {
    upstream
        .iter()
        .any(|(stored_kind, stored_name)| stored_kind == kind && stored_name == name)
}

fn short_hex(digest: &[u8]) -> String {
    let mut hex: String = String::with_capacity(KEPT_DIGEST_BYTES * 2);
    for byte in &digest[..KEPT_DIGEST_BYTES] {
        hex.push(char::from(HEX[usize::from(byte >> 4)]));
        hex.push(char::from(HEX[usize::from(byte & 0x0f)]));
    }
    hex
}

fn header_keys(values: &[(String, AuthoredValue)]) -> HeaderKeys {
    let mut keys: HeaderKeys = values
        .iter()
        .map(|(key, value)| {
            let mut encoding: ValueEncoding = ValueEncoding::default();
            encoding.value(value);
            let hex: String = short_hex(&bytes_digest(&encoding.bytes));
            (key.clone(), hex)
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
    (stored, upstream): (Option<&HeaderKeys>, &[(String, String)]),
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
    if !references_read(&parsed.query_sql, upstream) {
        return HeaderChange::Unsupported(format!("{relative_path} changed what it references"));
    }
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
