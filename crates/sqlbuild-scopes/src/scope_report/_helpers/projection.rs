//! The value-free metadata projection of one full scope index.

use sqlbuild_core::json::models::JsonValue;

use crate::scope_index::main::format_identity::format_identity;
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationRecord, QualifiedIdentity, ResourceIdentity,
};
use crate::scope_report::_helpers::declarations::{container, integer, optional_text, text, texts};
use crate::scope_report::_helpers::json::{diagnostic_json, object};
use crate::scope_report::_helpers::paths::safe_scope_path;
use crate::scope_report::constants::METADATA_SCHEMA_VERSION;
use crate::scope_report::models::{Completeness, DeclarationValues, ProjectionIndex};

fn resource_key(identity: &ResourceIdentity) -> String {
    format_identity(&QualifiedIdentity::Resource(identity.clone()))
}

fn declaration_key(identity: &DeclarationIdentity) -> String {
    format_identity(&QualifiedIdentity::Declaration(identity.clone()))
}

fn optional_key(identity: Option<&QualifiedIdentity>) -> String {
    identity.map(format_identity).unwrap_or_default()
}

/// Positions of `count` items in the stable order of `key`.
fn sorted<K: Ord>(count: usize, key: impl Fn(usize) -> K) -> Vec<usize> {
    let mut positions: Vec<usize> = (0..count).collect();
    positions.sort_by_cached_key(|position| key(*position));
    positions
}

fn declaration_metadata(values: Option<&DeclarationValues>) -> JsonValue {
    let mut metadata: Vec<(&str, JsonValue)> = Vec::new();
    let Some(values) = values else {
        return object(metadata);
    };
    if let Some(macro_values) = &values.macro_values {
        let mut dependencies: Vec<String> = macro_values
            .dependencies
            .iter()
            .map(declaration_key)
            .collect();
        dependencies.sort();
        metadata.push((
            "macro",
            object(vec![
                ("parameters", texts(&macro_values.parameters)),
                ("dependencies", texts(&dependencies)),
                ("source_digest", text(&macro_values.source_digest)),
            ]),
        ));
    }
    if let Some(enum_values) = &values.enum_values {
        let members: Vec<JsonValue> = enum_values
            .members
            .iter()
            .map(|member| object(vec![("name", text(member))]))
            .collect();
        metadata.push((
            "enum",
            object(vec![
                ("members", JsonValue::Array(members)),
                ("scalar_type", text(&enum_values.scalar_type)),
            ]),
        ));
    }
    if let Some(constant) = &values.constant_values {
        metadata.push((
            "constant",
            object(vec![
                ("logical_type", text(&constant.logical_type)),
                (
                    "collection_kind",
                    optional_text(constant.collection_kind.as_deref()),
                ),
                (
                    "item_count",
                    constant.item_count.map_or(JsonValue::Null, integer),
                ),
                ("nullable", JsonValue::Bool(constant.nullable)),
                ("render_as", optional_text(constant.render_as.as_deref())),
            ]),
        ));
    }
    object(metadata)
}

fn declaration_projection(
    record: &DeclarationRecord,
    values: Option<&DeclarationValues>,
) -> JsonValue {
    let (role, visibility, role_root, bucket) = container(record);
    object(vec![
        ("identity", text(&declaration_key(&record.identity))),
        ("kind", text(record.identity.kind.as_str())),
        ("name", text(&record.identity.name)),
        (
            "owner",
            record
                .identity
                .owner
                .as_ref()
                .map_or(JsonValue::Null, |owner| text(&resource_key(owner))),
        ),
        ("path", text(&safe_scope_path(&record.path))),
        ("line", integer(record.line)),
        ("column", integer(record.column)),
        ("scope", text(record.scope.as_str())),
        ("role", optional_text(role.as_deref())),
        ("visibility", text(visibility)),
        ("role_root", optional_text(role_root.as_deref())),
        ("bucket_path", optional_text(bucket.as_deref())),
        (
            "ownership_root",
            text(&safe_scope_path(&record.ownership_root.path)),
        ),
        (
            "owning_path",
            record
                .owning_path
                .as_deref()
                .map_or(JsonValue::Null, |path| text(&safe_scope_path(path))),
        ),
        ("metadata", declaration_metadata(values)),
    ])
}

fn completeness_json(completeness: Completeness) -> JsonValue {
    object(vec![
        ("discovery", JsonValue::Bool(completeness.discovery)),
        (
            "static_visibility",
            JsonValue::Bool(completeness.static_visibility),
        ),
        ("runtime_usage", JsonValue::Bool(completeness.runtime_usage)),
        ("relationships", JsonValue::Bool(completeness.relationships)),
        ("placement", JsonValue::Bool(completeness.placement)),
        (
            "promotion_impact",
            JsonValue::Bool(completeness.promotion_impact),
        ),
    ])
}

fn all_complete(completeness: Completeness) -> bool {
    completeness.discovery
        && completeness.static_visibility
        && completeness.runtime_usage
        && completeness.relationships
        && completeness.placement
        && completeness.promotion_impact
}

/// The projection Python's `build_projection` returns, as a JSON object.
pub(crate) fn projection(index: &ProjectionIndex) -> JsonValue {
    let roots: Vec<JsonValue> = sorted(index.roots.len(), |position| {
        let root = &index.roots[position];
        (
            root.path.clone(),
            root.resource_kind
                .map(crate::scope_index::models::ResourceKind::as_str)
                .unwrap_or_default(),
        )
    })
    .into_iter()
    .map(|position| {
        let root = &index.roots[position];
        object(vec![
            ("path", text(&safe_scope_path(&root.path))),
            (
                "resource_kind",
                optional_text(
                    root.resource_kind
                        .map(crate::scope_index::models::ResourceKind::as_str),
                ),
            ),
        ])
    })
    .collect();
    let resources: Vec<JsonValue> = sorted(index.resources.len(), |position| {
        let record = &index.resources[position];
        (resource_key(&record.identity), record.path.clone())
    })
    .into_iter()
    .map(|position| {
        let record = &index.resources[position];
        object(vec![
            ("identity", text(&resource_key(&record.identity))),
            ("kind", text(record.identity.kind.as_str())),
            ("name", text(&record.identity.name)),
            ("path", text(&safe_scope_path(&record.path))),
            (
                "ownership_root",
                text(&safe_scope_path(&record.ownership_root.path)),
            ),
            (
                "ownership_root_kind",
                optional_text(
                    record
                        .ownership_root
                        .resource_kind
                        .map(crate::scope_index::models::ResourceKind::as_str),
                ),
            ),
        ])
    })
    .collect();
    let declarations: Vec<JsonValue> = sorted(index.declarations.len(), |position| {
        let record = &index.declarations[position];
        (
            declaration_key(&record.identity),
            record.path.clone(),
            record.line,
            record.column,
        )
    })
    .into_iter()
    .map(|position| {
        declaration_projection(
            &index.declarations[position],
            index.values.declarations.get(position),
        )
    })
    .collect();
    let grants: Vec<JsonValue> = sorted(index.grants.len(), |position| {
        let grant = &index.grants[position];
        (
            resource_key(&grant.resource),
            declaration_key(&grant.declaration),
            format_identity(&grant.through),
            grant.kind.as_str(),
        )
    })
    .into_iter()
    .map(|position| {
        let grant = &index.grants[position];
        object(vec![
            ("resource", text(&resource_key(&grant.resource))),
            ("declaration", text(&declaration_key(&grant.declaration))),
            ("through", text(&format_identity(&grant.through))),
            ("kind", text(grant.kind.as_str())),
        ])
    })
    .collect();
    let usages: Vec<JsonValue> = sorted(index.usages.len(), |position| {
        let usage = &index.usages[position];
        (
            format_identity(&usage.consumer),
            declaration_key(&usage.declaration),
            usage.kind.clone(),
            optional_key(usage.through.as_ref()),
            usage.enum_member.clone().unwrap_or_default(),
        )
    })
    .into_iter()
    .map(|position| {
        let usage = &index.usages[position];
        object(vec![
            ("consumer", text(&format_identity(&usage.consumer))),
            ("declaration", text(&declaration_key(&usage.declaration))),
            ("kind", text(&usage.kind)),
            (
                "through",
                usage
                    .through
                    .as_ref()
                    .map_or(JsonValue::Null, |through| text(&format_identity(through))),
            ),
            ("enum_member", optional_text(usage.enum_member.as_deref())),
        ])
    })
    .collect();
    let visibility: Vec<JsonValue> = sorted(index.visibility.len(), |position| {
        let fact = &index.visibility[position];
        (
            resource_key(&fact.resource),
            declaration_key(&fact.declaration),
            fact.reason.clone(),
            optional_key(fact.through.as_ref()),
        )
    })
    .into_iter()
    .map(|position| {
        let fact = &index.visibility[position];
        object(vec![
            ("resource", text(&resource_key(&fact.resource))),
            ("declaration", text(&declaration_key(&fact.declaration))),
            ("reason", text(&fact.reason)),
            (
                "through",
                fact.through
                    .as_ref()
                    .map_or(JsonValue::Null, |through| text(&format_identity(through))),
            ),
        ])
    })
    .collect();
    let inaccessible: Vec<JsonValue> = sorted(index.inaccessible.len(), |position| {
        let fact = &index.inaccessible[position];
        (
            resource_key(&fact.resource),
            declaration_key(&fact.declaration),
            fact.reason.clone(),
        )
    })
    .into_iter()
    .map(|position| {
        let fact = &index.inaccessible[position];
        object(vec![
            ("resource", text(&resource_key(&fact.resource))),
            ("declaration", text(&declaration_key(&fact.declaration))),
            ("reason", text(&fact.reason)),
        ])
    })
    .collect();
    let diagnostics: Vec<JsonValue> = sorted(index.diagnostics.len(), |position| {
        let diagnostic = &index.diagnostics[position];
        (
            diagnostic.path.clone().unwrap_or_default(),
            diagnostic.line.unwrap_or(0),
            diagnostic.column.unwrap_or(0),
            diagnostic.code.clone(),
        )
    })
    .into_iter()
    .map(|position| diagnostic_json(&index.diagnostics[position]))
    .collect();
    let completeness: Completeness = index.values.completeness;
    object(vec![
        ("schema_version", integer(METADATA_SCHEMA_VERSION)),
        ("ownership_roots", JsonValue::Array(roots)),
        ("resources", JsonValue::Array(resources)),
        ("declarations", JsonValue::Array(declarations)),
        ("grants", JsonValue::Array(grants)),
        ("usages", JsonValue::Array(usages)),
        ("visibility", JsonValue::Array(visibility)),
        ("inaccessible", JsonValue::Array(inaccessible)),
        ("complete", JsonValue::Bool(all_complete(completeness))),
        ("completeness", completeness_json(completeness)),
        ("diagnostics", JsonValue::Array(diagnostics)),
    ])
}
