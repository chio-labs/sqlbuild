//! Python's SQL and Python function namespace and fingerprint namespace resolution.

use crate::functions::_helpers::namespace::part;
use crate::functions::models::{FunctionLanguage, FunctionNamespace, NamespaceInputs};

/// The physical, logical and fingerprint namespace Python's attachment assigns.
#[must_use]
pub fn resolve_function_namespace(inputs: &NamespaceInputs) -> FunctionNamespace {
    let inherit: bool =
        inputs.language == FunctionLanguage::Sql || inputs.inherit_default_namespace;
    let (database, logical_database, fingerprint_database, fingerprint_logical_database) = part(
        inputs.header_database.as_ref(),
        inputs.default_database.as_ref(),
        inputs.target_database.as_ref(),
        inherit,
    );
    let (schema, logical_schema, fingerprint_schema, fingerprint_logical_schema) = part(
        inputs.header_schema.as_ref(),
        inputs.default_schema.as_ref(),
        inputs.target_schema.as_ref(),
        inherit,
    );
    FunctionNamespace {
        database,
        schema,
        logical_database,
        logical_schema,
        fingerprint_database,
        fingerprint_schema,
        fingerprint_logical_database,
        fingerprint_logical_schema,
    }
}
