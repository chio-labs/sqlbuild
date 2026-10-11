//! Python's `decode_scope_index` validation: any fault is a cache miss.

use serde_json::{Map, Value};

use sqlbuild_core::json::models::{JsonInteger, JsonValue};

use crate::scope_cache::_helpers::json::{canonical_json, sha256_hex};
use crate::scope_cache::constants::{
    CACHE_SCHEMA_VERSION, COMPLETENESS_KEYS, DECLARATION_IDENTITY, RESOURCE_IDENTITY,
};
use crate::scope_cache::models::{
    CacheMiss, CachedDeclaration, CachedDiagnostic, CachedInaccessible, CachedIndex, CachedUsage,
    CachedVisibility, ConstantFacts, EnumFacts, MacroFacts,
};
use crate::scope_index::main::normalize_scope_path::normalize_scope_path;
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationKind, DeclarationRecord, GrantKind, OwnershipRoot,
    OwnershipRootKind, QualifiedIdentity, ReportGrant, ResourceIdentity, ResourceKind,
    ResourceRecord, ScopeKind,
};

/// A payload Python's decoder rejects.
pub(crate) struct Miss;

type Decoded<T> = Result<T, Miss>;

fn object(value: &Value) -> Decoded<&Map<String, Value>> {
    value.as_object().ok_or(Miss)
}

fn list<'a>(value: &'a Map<String, Value>, key: &str) -> Decoded<&'a Vec<Value>> {
    value.get(key).and_then(Value::as_array).ok_or(Miss)
}

fn string(value: &Map<String, Value>, key: &str) -> Decoded<String> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or(Miss)
}

fn integer(value: Option<&Value>) -> Decoded<i64> {
    value.and_then(Value::as_i64).ok_or(Miss)
}

fn boolean(value: &Map<String, Value>, key: &str) -> Decoded<bool> {
    value.get(key).and_then(Value::as_bool).ok_or(Miss)
}

fn optional_string(value: Option<&Value>) -> Decoded<Option<String>> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(Value::String(text)) => Ok(Some(text.clone())),
        Some(_) => Err(Miss),
    }
}

fn optional_integer(value: Option<&Value>) -> Decoded<Option<i64>> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(other) => integer(Some(other)).map(Some),
    }
}

fn path(text: &str) -> Decoded<String> {
    normalize_scope_path(text).map_err(|_| Miss)
}

fn optional_path(value: Option<&Value>) -> Decoded<Option<String>> {
    optional_string(value)?.as_deref().map(path).transpose()
}

fn identity(value: Option<&Value>) -> Decoded<QualifiedIdentity> {
    let item = object(value.ok_or(Miss)?)?;
    let kind: String = string(item, "kind")?;
    let name: String = string(item, "name")?;
    match item.get("type").and_then(Value::as_str) {
        Some(RESOURCE_IDENTITY) => Ok(QualifiedIdentity::Resource(ResourceIdentity {
            kind: ResourceKind::parse(&kind).ok_or(Miss)?,
            name,
        })),
        Some(DECLARATION_IDENTITY) => {
            let owner: Option<ResourceIdentity> = match item.get("owner") {
                None | Some(Value::Null) => None,
                Some(owner) => Some(resource(Some(owner))?),
            };
            Ok(QualifiedIdentity::Declaration(DeclarationIdentity {
                kind: DeclarationKind::parse(&kind).ok_or(Miss)?,
                name,
                owner,
            }))
        }
        _ => Err(Miss),
    }
}

fn optional_identity(value: Option<&Value>) -> Decoded<Option<QualifiedIdentity>> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(other) => identity(Some(other)).map(Some),
    }
}

fn resource(value: Option<&Value>) -> Decoded<ResourceIdentity> {
    match identity(value)? {
        QualifiedIdentity::Resource(identity) => Ok(identity),
        QualifiedIdentity::Declaration(_) => Err(Miss),
    }
}

fn declaration(value: Option<&Value>) -> Decoded<DeclarationIdentity> {
    match identity(value)? {
        QualifiedIdentity::Declaration(identity) => Ok(identity),
        QualifiedIdentity::Resource(_) => Err(Miss),
    }
}

fn root(value: Option<&Value>) -> Decoded<OwnershipRoot> {
    let item = object(value.ok_or(Miss)?)?;
    let resource_kind: Option<ResourceKind> = match item.get("resource_kind") {
        Some(Value::String(kind)) => Some(ResourceKind::parse(kind).ok_or(Miss)?),
        _ => None,
    };
    Ok(OwnershipRoot {
        path: path(&string(item, "path")?)?,
        kind: OwnershipRootKind::parse(&string(item, "kind")?).ok_or(Miss)?,
        resource_kind,
    })
}

fn macro_facts(value: &Value) -> Decoded<MacroFacts> {
    let item = object(value)?;
    let mut dependencies: Vec<DeclarationIdentity> = Vec::new();
    for raw in list(item, "dependencies")? {
        dependencies.push(declaration(Some(raw))?);
    }
    let mut parameters: Vec<String> = Vec::new();
    for raw in list(item, "parameters")? {
        parameters.push(raw.as_str().ok_or(Miss)?.to_owned());
    }
    Ok(MacroFacts {
        parameters,
        dependencies,
        source_digest: string(item, "source_digest")?,
    })
}

fn enum_facts(value: &Value) -> Decoded<EnumFacts> {
    let item = object(value)?;
    let mut members: Vec<String> = Vec::new();
    for raw in list(item, "members")? {
        let member = object(raw)?;
        if member.len() != 1 {
            return Err(Miss);
        }
        members.push(string(member, "name")?);
    }
    Ok(EnumFacts {
        members,
        scalar_type: string(item, "scalar_type")?,
    })
}

fn constant_facts(value: &Value) -> Decoded<ConstantFacts> {
    let item = object(value)?;
    Ok(ConstantFacts {
        logical_type: string(item, "logical_type")?,
        collection_kind: optional_string(item.get("collection_kind"))?,
        item_count: optional_integer(item.get("item_count"))?,
        nullable: boolean(item, "nullable")?,
        render_as: optional_string(item.get("render_as"))?,
    })
}

fn optional<T>(value: Option<&Value>, decode: fn(&Value) -> Decoded<T>) -> Decoded<Option<T>> {
    match value {
        None | Some(Value::Null) => Ok(None),
        Some(other) => decode(other).map(Some),
    }
}

fn cached_declaration(value: &Value) -> Decoded<CachedDeclaration> {
    let item = object(value)?;
    let identity: DeclarationIdentity = declaration(item.get("identity"))?;
    let macro_facts: Option<MacroFacts> = optional(item.get("macro"), macro_facts)?;
    let enum_facts: Option<EnumFacts> = optional(item.get("enum"), enum_facts)?;
    let constant_facts: Option<ConstantFacts> = optional(item.get("constant"), constant_facts)?;
    Ok(CachedDeclaration {
        record: DeclarationRecord {
            identity,
            path: path(&string(item, "path")?)?,
            line: integer(item.get("line"))?,
            column: integer(item.get("column"))?,
            scope: ScopeKind::parse(&string(item, "scope")?).ok_or(Miss)?,
            ownership_root: root(item.get("ownership_root"))?,
            owning_path: optional_path(item.get("owning_path"))?,
            dependencies: Vec::new(),
        },
        macro_facts,
        enum_facts,
        constant_facts,
    })
}

fn grant_kind(value: &str) -> Decoded<GrantKind> {
    [GrantKind::ExpectedModel, GrantKind::TestedMacro]
        .into_iter()
        .find(|kind| kind.as_str() == value)
        .ok_or(Miss)
}

fn usage(value: &Value) -> Decoded<CachedUsage> {
    let item = object(value)?;
    let consumer: QualifiedIdentity = identity(item.get("consumer"))?;
    let declared: QualifiedIdentity = identity(item.get("declaration"))?;
    let through: Option<QualifiedIdentity> = optional_identity(item.get("through"))?;
    let QualifiedIdentity::Declaration(declaration) = declared else {
        return Err(Miss);
    };
    Ok(CachedUsage {
        consumer,
        declaration,
        kind: string(item, "kind")?,
        through,
        enum_member: optional_string(item.get("enum_member"))?,
    })
}

fn grant(value: &Value) -> Decoded<ReportGrant> {
    let item = object(value)?;
    Ok(ReportGrant {
        resource: resource(item.get("resource"))?,
        declaration: declaration(item.get("declaration"))?,
        through: identity(item.get("through"))?,
        kind: grant_kind(&string(item, "kind")?)?,
    })
}

fn visibility(value: &Value) -> Decoded<CachedVisibility> {
    let item = object(value)?;
    Ok(CachedVisibility {
        resource: resource(item.get("resource"))?,
        declaration: declaration(item.get("declaration"))?,
        reason: string(item, "reason")?,
        through: optional_identity(item.get("through"))?,
    })
}

fn inaccessible(value: &Value) -> Decoded<CachedInaccessible> {
    let item = object(value)?;
    Ok(CachedInaccessible {
        resource: resource(item.get("resource"))?,
        declaration: declaration(item.get("declaration"))?,
        reason: string(item, "reason")?,
    })
}

fn diagnostic(value: &Value) -> Decoded<CachedDiagnostic> {
    let item = object(value)?;
    let declaration: Option<DeclarationIdentity> = match item.get("declaration") {
        None | Some(Value::Null) => None,
        Some(other) => Some(declaration(Some(other))?),
    };
    let resource: Option<ResourceIdentity> = match item.get("resource") {
        None | Some(Value::Null) => None,
        Some(other) => Some(resource(Some(other))?),
    };
    Ok(CachedDiagnostic {
        code: string(item, "code")?,
        message: string(item, "message")?,
        severity: string(item, "severity")?,
        path: optional_path(item.get("path"))?,
        line: optional_integer(item.get("line"))?,
        column: optional_integer(item.get("column"))?,
        declaration,
        resource,
    })
}

fn records<T>(
    value: &Map<String, Value>,
    key: &str,
    decode: fn(&Value) -> Decoded<T>,
) -> Decoded<Vec<T>> {
    list(value, key)?.iter().map(decode).collect()
}

fn resource_record(value: &Value) -> Decoded<ResourceRecord> {
    let item = object(value)?;
    Ok(ResourceRecord {
        identity: resource(item.get("identity"))?,
        path: path(&string(item, "path")?)?,
        ownership_root: root(item.get("ownership_root"))?,
    })
}

fn root_record(value: &Value) -> Decoded<OwnershipRoot> {
    root(Some(value))
}

/// The full index a payload holds, as Python's `decode_scope_index` reads it.
pub(crate) fn decode_index(payload: &Value) -> Decoded<CachedIndex> {
    let value = object(payload)?;
    let roots: Vec<OwnershipRoot> = records(value, "ownership_roots", root_record)?;
    let resources: Vec<ResourceRecord> = records(value, "resources", resource_record)?;
    let declarations: Vec<CachedDeclaration> = records(value, "declarations", cached_declaration)?;
    let usages: Vec<CachedUsage> = records(value, "usages", usage)?;
    let grants: Vec<ReportGrant> = records(value, "grants", grant)?;
    let visibility: Vec<CachedVisibility> = records(value, "visibility", visibility)?;
    let inaccessible: Vec<CachedInaccessible> = records(value, "inaccessible", inaccessible)?;
    let diagnostics: Vec<CachedDiagnostic> = records(value, "diagnostics", diagnostic)?;
    let flags = object(value.get("completeness").ok_or(Miss)?)?;
    let mut completeness: [bool; 6] = [false; 6];
    for (slot, key) in completeness.iter_mut().zip(COMPLETENESS_KEYS) {
        *slot = boolean(flags, key)?;
    }
    Ok(CachedIndex {
        roots,
        resources,
        declarations,
        usages,
        grants,
        visibility,
        inaccessible,
        diagnostics,
        completeness,
    })
}

/// A parsed JSON value as the emitter's value; `Miss` for numbers Python reads differently.
fn json_value(value: &Value) -> Decoded<JsonValue> {
    Ok(match value {
        Value::Null => JsonValue::Null,
        Value::Bool(flag) => JsonValue::Bool(*flag),
        Value::Number(number) if number.is_i64() || number.is_u64() => {
            JsonValue::Integer(JsonInteger::parse(&number.to_string()).ok_or(Miss)?)
        }
        Value::Number(number) => JsonValue::Float(number.as_f64().ok_or(Miss)?),
        Value::String(text) => JsonValue::String(text.clone()),
        Value::Array(items) => {
            JsonValue::Array(items.iter().map(json_value).collect::<Decoded<_>>()?)
        }
        Value::Object(fields) => {
            let mut entries: Vec<(String, JsonValue)> = Vec::with_capacity(fields.len());
            for (key, item) in fields {
                entries.push((key.clone(), json_value(item)?));
            }
            JsonValue::Object(entries)
        }
    })
}

/// The cached index in `raw` for `fingerprint`, as `read_cached_scope_index` checks it.
pub(crate) fn decode_envelope(raw: &[u8], fingerprint: &str) -> Result<CachedIndex, CacheMiss> {
    let text: &str = std::str::from_utf8(raw).map_err(|_| CacheMiss::Unreadable)?;
    let envelope: Value = serde_json::from_str(text).map_err(|_| CacheMiss::Unreadable)?;
    let envelope = envelope.as_object().ok_or(CacheMiss::Stale)?;
    let field =
        |key: &str| -> Result<&Value, CacheMiss> { envelope.get(key).ok_or(CacheMiss::Stale) };
    if field("schema_version")?.as_i64() != Some(CACHE_SCHEMA_VERSION)
        || field("input_fingerprint")?.as_str() != Some(fingerprint)
    {
        return Err(CacheMiss::Stale);
    }
    let payload: &Value = field("payload")?;
    let canonical: String = json_value(payload)
        .map_err(|Miss| CacheMiss::Stale)
        .and_then(|value| canonical_json(&value).map_err(|_| CacheMiss::Stale))?;
    if field("payload_sha256")?.as_str() != Some(sha256_hex(canonical.as_bytes()).as_str()) {
        return Err(CacheMiss::Stale);
    }
    decode_index(payload).map_err(|Miss| CacheMiss::Invalid)
}
