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
}

/// `(name, type, nullability)` of one inferred output column.
pub type InferredRow = (String, Option<String>, String);
