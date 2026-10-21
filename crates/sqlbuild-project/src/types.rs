//! What the host supplies beside each compiled record.

use std::fmt::Debug;

/// The host's own values and lazily built views, kept in one slot beside each compiled record.
pub trait ProjectHost {
    /// A model input's host values: its model file, config, declarations, usages and views.
    type ModelInput: Debug;
    /// A model schema's host values: its header columns, audits and dynamic columns.
    type Schema: Debug;
    /// A compiled model's lazily built views.
    type CompiledModel: Debug;
    /// A model analysis's lazily built views.
    type Analysis: Debug;
    /// An attached source's host values: its file, entry, metadata, specs and usages.
    type AttachedSource: Debug;
    /// A source record's lazily built facts and views.
    type Source: Debug;
    /// An attached function's host values: its file and usages.
    type AttachedFunction: Debug;
    /// A function record's lazily built views.
    type Function: Debug;
    /// An attached audit's host values: its file, block, measurement policy specs and usages.
    type AttachedAudit: Debug;
    /// An audit record's lazily built views.
    type Audit: Debug;
    /// A seed's host values: its CSV file, declaration, schema file and views.
    type Seed: Debug;
}

/// `(name, type, nullability)` of one inferred output column.
pub type InferredRow = (String, Option<String>, String);

/// `(database, schema)` native project assembly resolved for a source, or `None`.
pub type SourceNamespace = Option<(Option<String>, Option<String>)>;

/// `(name, type)` of a function argument or return column, its types template-expanded.
pub type NamedTypeRow = (String, String);

/// `(kind, name)` of a compiled object key.
pub type ObjectKeyRow = (String, String);
