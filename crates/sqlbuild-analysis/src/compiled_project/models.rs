//! Facts a compile's producers retain about each resource, in production order.

use std::collections::{BTreeMap, HashMap};

use serde_json::Value;

/// One compile's project facts; models keep the order the compile-input stage produced them.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct CompiledProjectFacts {
    pub(crate) models: Vec<CompiledModelFacts>,
    pub(crate) model_index: HashMap<String, usize>,
}

/// What the compile-input stage produced for one model, plus its analysis once transferred.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct CompiledModelFacts {
    pub name: String,
    pub relative_path: String,
    /// SQL after variable, declaration and macro expansion.
    pub query_sql: String,
    /// The authored query below the `MODEL (...)` header.
    pub authored_query_sql: String,
    /// The whole authored file.
    pub authored_sql: String,
    pub config: ModelConfigFacts,
    pub references: Vec<ModelReferenceFact>,
    pub schema: Option<ModelSchemaFact>,
    pub enum_columns: Vec<String>,
    pub enum_declarations: Vec<DeclarationFact>,
    pub constant_declarations: Vec<DeclarationFact>,
    /// The typed analysis result; `None` until the assembly stage transfers it.
    pub analysis: Option<ModelAnalysisFact>,
}

/// A model's effective config values with sorted keys, as the rules request has always read them.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct ModelConfigFacts {
    pub values: BTreeMap<String, Value>,
    /// Why the values could not be encoded, raised only when a consumer reads them.
    pub encoding_error: Option<String>,
    pub header_keys: Vec<String>,
    pub layer_schema: Option<String>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ModelReferenceFact {
    pub kind: String,
    pub name: String,
    pub package: Option<String>,
}

/// A model's declared schema entry.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ModelSchemaFact {
    /// Audits declared on the entry itself, not on its columns.
    pub audit_count: u32,
    pub columns: Vec<SchemaColumnFact>,
    pub dynamic_columns: Vec<DynamicFamilyFact>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SchemaColumnFact {
    pub name: String,
    pub data_type: Option<String>,
    pub nullable: Option<bool>,
    pub audit_count: u32,
}

/// One declared dynamic-column family; `key` is its name casefolded.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DynamicFamilyFact {
    pub key: String,
    pub name: String,
    pub pivot_column: String,
    pub value_column: String,
    pub aggregate: String,
    pub data_type: String,
    pub name_pattern: Option<String>,
}

/// An enum or constant declaration a model can see.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DeclarationFact {
    pub name: String,
    pub relative_path: String,
    pub members: Vec<(String, Value)>,
    pub value: Option<Value>,
    pub value_type: Option<String>,
    pub render_as: Option<String>,
}

/// A model's typed analysis outcome: inferred output columns and its dynamic pivot proof.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ModelAnalysisFact {
    /// Each inferred output column's name and type, in output order.
    pub inferred_columns: Vec<(String, Option<String>)>,
    pub dynamic_proof: Option<DynamicProofFact>,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DynamicProofFact {
    pub output_proven: bool,
    pub bare_dynamic_pivot: bool,
    /// `(family key, inferred type)` per declared family.
    pub families: Vec<(String, Option<String>)>,
}
