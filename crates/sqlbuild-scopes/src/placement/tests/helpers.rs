use crate::placement::models::{PlacementIndex, PlacementUsage};
use crate::scope_index::models::{
    DeclarationIdentity, DeclarationKind, DeclarationRecord, OwnershipRoot, OwnershipRootKind,
    QualifiedIdentity, ResourceIdentity, ResourceKind, ResourceRecord, ScopeKind,
};

pub(super) fn model(name: &str) -> ResourceIdentity {
    ResourceIdentity {
        kind: ResourceKind::Model,
        name: name.to_owned(),
    }
}

fn macro_identity(name: &str) -> DeclarationIdentity {
    DeclarationIdentity {
        kind: DeclarationKind::Macro,
        name: name.to_owned(),
        owner: None,
    }
}

fn models_root() -> OwnershipRoot {
    OwnershipRoot {
        path: "models".to_owned(),
        kind: OwnershipRootKind::Resource,
        resource_kind: Some(ResourceKind::Model),
    }
}

fn model_record(name: &str, path: &str) -> ResourceRecord {
    ResourceRecord {
        identity: model(name),
        path: path.to_owned(),
        ownership_root: models_root(),
    }
}

/// A macro declared at `path` with `scope` and `owning_path` below the models root.
fn macro_record(name: &str, path: &str, placement: (ScopeKind, Option<&str>)) -> DeclarationRecord {
    let (scope, owning_path) = placement;
    DeclarationRecord {
        identity: macro_identity(name),
        path: path.to_owned(),
        line: 1,
        column: 0,
        scope,
        ownership_root: models_root(),
        owning_path: owning_path.map(str::to_owned),
        dependencies: Vec::new(),
    }
}

fn runtime(consumer: &str, declaration: &str) -> PlacementUsage {
    PlacementUsage {
        consumer: QualifiedIdentity::Resource(model(consumer)),
        declaration: macro_identity(declaration),
        through: None,
    }
}

const SALES: (ScopeKind, Option<&str>) = (ScopeKind::Local, Some("models/sales"));

/// A model and a descendant-folder model, a local macro both use, and an unused global macro.
pub(super) fn descendant_models() -> PlacementIndex {
    PlacementIndex {
        resources: vec![
            model_record("orders", "models/sales/orders.sql"),
            model_record("customers", "models/sales/crm/customers.sql"),
        ],
        declarations: vec![
            macro_record("cents", "models/sales/_macros/cents.py", SALES),
            macro_record("unused", "macros/unused.py", (ScopeKind::Global, None)),
            macro_record("shared", "models/sales/_macros/shared.py", SALES),
        ],
        usages: vec![
            runtime("orders", "cents"),
            runtime("orders", "shared"),
            runtime("customers", "shared"),
        ],
    }
}

/// One model using a local macro, which a further macro uses in turn.
pub(super) fn chained_macros() -> PlacementIndex {
    PlacementIndex {
        resources: vec![model_record("orders", "models/sales/orders.sql")],
        declarations: vec![
            macro_record("cents", "models/sales/_macros/cents.py", SALES),
            macro_record("round", "models/sales/_macros/round.py", SALES),
        ],
        usages: vec![
            runtime("orders", "cents"),
            PlacementUsage {
                consumer: QualifiedIdentity::Declaration(macro_identity("cents")),
                declaration: macro_identity("round"),
                through: None,
            },
        ],
    }
}

/// Owned `(declaration, path, owning path)` rows of expected relocations.
pub(super) fn owned_relocations(
    items: &[(usize, &str, Option<&str>)],
) -> Vec<(usize, String, Option<String>)> {
    items
        .iter()
        .map(|(position, path, owning)| (*position, (*path).to_owned(), owning.map(str::to_owned)))
        .collect()
}
