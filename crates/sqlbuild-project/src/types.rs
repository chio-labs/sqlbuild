//! What the host supplies beside each compiled record.

use std::fmt::Debug;

/// The host's own values and lazily built views, kept in one slot beside each compiled record.
pub trait ProjectHost {
    /// A model input's host values: its model file, config, declarations, usages and views.
    type ModelInput: Debug;
    /// A model schema's host values: its header columns, audits and dynamic columns.
    type Schema: Debug;
    /// What assembly and the semantic checks finished for a compiled model.
    type CompiledModel: Debug;
}
