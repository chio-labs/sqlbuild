//! The cache payload of a full scope index in the lookup's canonical order.

use sqlbuild_core::json::models::JsonValue;

use crate::scope_cache::_helpers::json::{integer, object, optional_integer, optional_text, text};
use crate::scope_cache::constants::{COMPLETENESS_KEYS, DECLARATION_IDENTITY, RESOURCE_IDENTITY};
use crate::scope_cache::models::{CachedDeclaration, CachedIndex};
use crate::scope_index::main::format_identity::format_identity;
use crate::scope_index::main::normalize_scope_path::normalize_scope_path;
use crate::scope_index::models::{
    DeclarationIdentity, OwnershipRoot, QualifiedIdentity, ReportLookup, ResourceIdentity,
    ResourceKind,
};

/// A path the payload cannot normalize, which makes Python skip the cache write.
pub(crate) struct Unwritable;

fn path(value: &str) -> Result<JsonValue, Unwritable> {
    normalize_scope_path(value)
        .map(JsonValue::String)
        .map_err(|_| Unwritable)
}

fn optional_path(value: Option<&str>) -> Result<JsonValue, Unwritable> {
    value.map_or(Ok(JsonValue::Null), path)
}

pub(crate) fn resource_identity(identity: &ResourceIdentity) -> JsonValue {
    object(vec![
        ("type", text(RESOURCE_IDENTITY)),
        ("kind", text(identity.kind.as_str())),
        ("name", text(&identity.name)),
    ])
}

pub(crate) fn declaration_identity(identity: &DeclarationIdentity) -> JsonValue {
    object(vec![
        ("type", text(DECLARATION_IDENTITY)),
        ("kind", text(identity.kind.as_str())),
        ("name", text(&identity.name)),
        (
            "owner",
            identity
                .owner
                .as_ref()
                .map_or(JsonValue::Null, resource_identity),
        ),
    ])
}

pub(crate) fn qualified_identity(identity: &QualifiedIdentity) -> JsonValue {
    match identity {
        QualifiedIdentity::Resource(identity) => resource_identity(identity),
        QualifiedIdentity::Declaration(identity) => declaration_identity(identity),
    }
}

fn optional_identity(identity: Option<&QualifiedIdentity>) -> JsonValue {
    identity.map_or(JsonValue::Null, qualified_identity)
}

fn root(root: &OwnershipRoot) -> Result<JsonValue, Unwritable> {
    Ok(object(vec![
        ("path", path(&root.path)?),
        ("kind", text(root.kind.as_str())),
        (
            "resource_kind",
            optional_text(root.resource_kind.map(ResourceKind::as_str)),
        ),
    ]))
}

fn declaration(item: &CachedDeclaration) -> Result<JsonValue, Unwritable> {
    let record = &item.record;
    let macro_facts: JsonValue = item.macro_facts.as_ref().map_or(JsonValue::Null, |facts| {
        object(vec![
            (
                "parameters",
                JsonValue::Array(facts.parameters.iter().map(|value| text(value)).collect()),
            ),
            (
                "dependencies",
                JsonValue::Array(
                    facts
                        .dependencies
                        .iter()
                        .map(declaration_identity)
                        .collect(),
                ),
            ),
            ("source_digest", text(&facts.source_digest)),
        ])
    });
    let enum_facts: JsonValue = item.enum_facts.as_ref().map_or(JsonValue::Null, |facts| {
        object(vec![
            (
                "members",
                JsonValue::Array(
                    facts
                        .members
                        .iter()
                        .map(|name| object(vec![("name", text(name))]))
                        .collect(),
                ),
            ),
            ("scalar_type", text(&facts.scalar_type)),
        ])
    });
    let constant_facts: JsonValue = item
        .constant_facts
        .as_ref()
        .map_or(JsonValue::Null, |facts| {
            object(vec![
                ("logical_type", text(&facts.logical_type)),
                (
                    "collection_kind",
                    optional_text(facts.collection_kind.as_deref()),
                ),
                ("item_count", optional_integer(facts.item_count)),
                ("nullable", JsonValue::Bool(facts.nullable)),
                ("render_as", optional_text(facts.render_as.as_deref())),
            ])
        });
    Ok(object(vec![
        ("identity", declaration_identity(&record.identity)),
        ("path", path(&record.path)?),
        ("line", integer(record.line)),
        ("column", integer(record.column)),
        ("scope", text(record.scope.as_str())),
        ("ownership_root", root(&record.ownership_root)?),
        ("owning_path", optional_path(record.owning_path.as_deref())?),
        ("macro", macro_facts),
        ("enum", enum_facts),
        ("constant", constant_facts),
    ]))
}

fn resource_text(identity: &ResourceIdentity) -> String {
    format_identity(&QualifiedIdentity::Resource(identity.clone()))
}

fn declaration_text(identity: &DeclarationIdentity) -> String {
    format_identity(&QualifiedIdentity::Declaration(identity.clone()))
}

/// Stable positions of `count` items ordered by `key`.
fn ordered<K: Ord>(count: usize, key: impl Fn(usize) -> K) -> Vec<usize> {
    let mut positions: Vec<usize> = (0..count).collect();
    positions.sort_by_cached_key(|position| key(*position));
    positions
}

fn array(
    order: &[usize],
    item: impl Fn(usize) -> Result<JsonValue, Unwritable>,
) -> Result<JsonValue, Unwritable> {
    Ok(JsonValue::Array(
        order
            .iter()
            .map(|position| item(*position))
            .collect::<Result<_, _>>()?,
    ))
}

/// The payload object Python's `_index_payload` builds for the canonical index.
pub(crate) fn index_payload(
    index: &CachedIndex,
    lookup: &ReportLookup,
) -> Result<JsonValue, Unwritable> {
    let visibility: Vec<usize> = ordered(index.visibility.len(), |position| {
        let item = &index.visibility[position];
        (
            resource_text(&item.resource),
            declaration_text(&item.declaration),
            item.reason.clone(),
            item.through
                .as_ref()
                .map(format_identity)
                .unwrap_or_default(),
        )
    });
    let inaccessible: Vec<usize> = ordered(index.inaccessible.len(), |position| {
        let item = &index.inaccessible[position];
        (
            resource_text(&item.resource),
            declaration_text(&item.declaration),
            item.reason.clone(),
        )
    });
    Ok(object(vec![
        (
            "ownership_roots",
            array(&lookup.roots, |position| root(&index.roots[position]))?,
        ),
        (
            "resources",
            array(&lookup.resources, |position| {
                let record = &index.resources[position];
                Ok(object(vec![
                    ("identity", resource_identity(&record.identity)),
                    ("path", path(&record.path)?),
                    ("ownership_root", root(&record.ownership_root)?),
                ]))
            })?,
        ),
        (
            "declarations",
            array(&lookup.declarations, |position| {
                declaration(&index.declarations[position])
            })?,
        ),
        (
            "usages",
            array(&lookup.usages, |position| {
                let item = &index.usages[position];
                Ok(object(vec![
                    ("consumer", qualified_identity(&item.consumer)),
                    ("declaration", declaration_identity(&item.declaration)),
                    ("kind", text(&item.kind)),
                    ("through", optional_identity(item.through.as_ref())),
                    ("enum_member", optional_text(item.enum_member.as_deref())),
                ]))
            })?,
        ),
        (
            "grants",
            array(&lookup.grants, |position| {
                let item = &index.grants[position];
                Ok(object(vec![
                    ("resource", resource_identity(&item.resource)),
                    ("declaration", declaration_identity(&item.declaration)),
                    ("through", qualified_identity(&item.through)),
                    ("kind", text(item.kind.as_str())),
                ]))
            })?,
        ),
        (
            "visibility",
            array(&visibility, |position| {
                let item = &index.visibility[position];
                Ok(object(vec![
                    ("resource", resource_identity(&item.resource)),
                    ("declaration", declaration_identity(&item.declaration)),
                    ("reason", text(&item.reason)),
                    ("through", optional_identity(item.through.as_ref())),
                ]))
            })?,
        ),
        (
            "inaccessible",
            array(&inaccessible, |position| {
                let item = &index.inaccessible[position];
                Ok(object(vec![
                    ("resource", resource_identity(&item.resource)),
                    ("declaration", declaration_identity(&item.declaration)),
                    ("reason", text(&item.reason)),
                ]))
            })?,
        ),
        (
            "diagnostics",
            array(&lookup.diagnostics, |position| {
                let item = &index.diagnostics[position];
                Ok(object(vec![
                    ("code", text(&item.code)),
                    ("message", text(&item.message)),
                    ("severity", text(&item.severity)),
                    ("path", optional_path(item.path.as_deref())?),
                    ("line", optional_integer(item.line)),
                    ("column", optional_integer(item.column)),
                    (
                        "declaration",
                        item.declaration
                            .as_ref()
                            .map_or(JsonValue::Null, declaration_identity),
                    ),
                    (
                        "resource",
                        item.resource
                            .as_ref()
                            .map_or(JsonValue::Null, resource_identity),
                    ),
                ]))
            })?,
        ),
        (
            "completeness",
            object(
                COMPLETENESS_KEYS
                    .iter()
                    .zip(index.completeness)
                    .map(|(key, complete)| (*key, JsonValue::Bool(complete)))
                    .collect(),
            ),
        ),
    ]))
}
