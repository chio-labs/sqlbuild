use crate::scope_index::models::VisibilityReason;

/// `(kind, name, path)` of one resource in walk order.
pub(super) type ResourceRow = (&'static str, &'static str, &'static str);

/// `(kind, name, path, line, scope, owning path)` of one declaration in walk order.
pub(super) type DeclarationRow = (
    &'static str,
    &'static str,
    &'static str,
    i64,
    &'static str,
    Option<&'static str>,
);

/// `(test name, expected models, called macros, tested macros)`.
pub(super) type FactRow = (
    &'static str,
    &'static [&'static str],
    &'static [&'static str],
    &'static [&'static str],
);

/// One scope-index case: authored resources and declarations, then the expected projection.
pub(super) struct IndexTestCase {
    pub(super) description: &'static str,
    pub(super) resources: &'static [ResourceRow],
    pub(super) declarations: &'static [DeclarationRow],
    /// Resource identities in the builder's order.
    pub(super) expected_resource_order: &'static [&'static str],
    /// Resource identities in the lookup's canonical order.
    pub(super) expected_canonical_resources: &'static [&'static str],
    /// `path:line` of declarations in the builder's order.
    pub(super) expected_declaration_order: &'static [&'static str],
    /// `path:line` of declarations in the lookup's canonical order.
    pub(super) expected_canonical_declarations: &'static [&'static str],
    /// `code message` diagnostics in the builder's order.
    pub(super) expected_diagnostics: &'static [&'static str],
}

/// One case whose only expectation is whether the native stage defers to Python.
pub(super) struct DeferralTestCase {
    pub(super) description: &'static str,
    pub(super) resources: &'static [ResourceRow],
    pub(super) declarations: &'static [DeclarationRow],
    pub(super) expected_deferral: bool,
}

/// One case for the relationship flag and the macro dependency usages.
pub(super) struct IndexFactsTestCase {
    pub(super) description: &'static str,
    pub(super) declarations: &'static [DeclarationRow],
    /// Dependency names of the first declaration, which must be a macro.
    pub(super) dependencies: &'static [&'static str],
    pub(super) expected_scoped_relationships: bool,
    /// `consumer -> dependency` usages in the builder's order.
    pub(super) expected_usages: &'static [&'static str],
}

/// One relationship case: a scoped project, the extracted facts and the expected grants.
pub(super) struct GrantTestCase {
    pub(super) description: &'static str,
    pub(super) resources: &'static [ResourceRow],
    pub(super) declarations: &'static [DeclarationRow],
    pub(super) facts: &'static [FactRow],
    /// `resource declaration through kind` qualified identities.
    pub(super) expected_grants: &'static [&'static str],
}

/// One lookup case: resources and declarations, the resource groups and visibility positions.
pub(super) struct LookupTestCase {
    pub(super) description: &'static str,
    pub(super) resources: &'static [ResourceRow],
    pub(super) declarations: &'static [DeclarationRow],
    /// First resource identity of each resource group, in mapping order.
    pub(super) expected_resource_groups: &'static [&'static str],
    pub(super) expected_repr_ordered: bool,
    /// `global`, `private`, `local` and `inherited` position groups as text.
    pub(super) expected_visibility: &'static [&'static str],
}

/// One Python `repr` case for a lookup key string.
pub(super) struct ReprTestCase {
    pub(super) description: &'static str,
    pub(super) value: &'static str,
    pub(super) expected_repr: Option<&'static str>,
}

/// `(position, reason, through)` of one visible record.
pub(super) type VisibleRow = (usize, &'static str, Option<usize>);

/// One consumer path, its private positions and `(identity key, reason, through)` grants.
pub(super) struct ClassifyTestCase {
    pub(super) description: &'static str,
    pub(super) path: &'static str,
    pub(super) private: &'static [usize],
    pub(super) grants: &'static [(u32, VisibilityReason, usize)],
    pub(super) expected_classified: Option<(&'static [VisibleRow], &'static [usize])>,
}
