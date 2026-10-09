//! Plain-data contract requests and the diagnostics native contract validation returns.

/// The models of one compiled project whose column contracts are evaluated together.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractRequest {
    /// The dialect name Python hands type normalization (`str(dialect or "generic")`).
    pub dialect: String,
    /// Whether `settings.column_contract_mode` is `implicit`.
    pub implicit_column_contracts: bool,
    pub models: Vec<ContractModel>,
}

/// One compiled model's contract inputs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractModel {
    pub name: String,
    /// The `contract` config value when it is a string.
    pub contract: Option<String>,
    /// The model's schema entry, when it has one.
    pub schema: Option<ContractSchema>,
    /// Inferred output columns, or None when static analysis inferred none.
    pub inferred_columns: Option<Vec<InferredOutputColumn>>,
    pub fast_lineage_has_star: bool,
    pub dynamic_proof: Option<DynamicContractProof>,
    pub unchecked_output_columns: Vec<String>,
}

/// The declared shape of one model.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractSchema {
    pub columns: Vec<DeclaredColumn>,
    pub dynamic_columns: Vec<DeclaredColumnFamily>,
    pub type_enforcement: bool,
    /// Whether the columns come from a named SCHEMA.
    pub named_schema: bool,
}

/// One declared column.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeclaredColumn {
    pub name: String,
    pub declared_type: Option<String>,
    /// Whether the column declares `nullable false`.
    pub not_null: bool,
    /// Whether the column is declared in a named SCHEMA file other than the model file.
    pub declared_in_named_schema: bool,
}

/// One declared runtime-generated column family.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeclaredColumnFamily {
    pub name: String,
    pub declared_type: String,
}

/// One statically inferred output column.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InferredOutputColumn {
    pub name: String,
    pub inferred_type: Option<String>,
    /// Whether the column is proven nullable.
    pub nullable: bool,
}

/// Compiler evidence for a dynamic column contract.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DynamicContractProof {
    pub output_proven: bool,
    pub failure_reason: Option<String>,
    /// `(family name, inferred type)` in proof order.
    pub families: Vec<(String, Option<String>)>,
}

/// The severity of one contract diagnostic.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContractSeverity {
    Error,
    Warning,
}

/// Where a contract diagnostic points.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ContractLocation {
    None,
    /// The declared column at this index of the model's schema columns.
    Declared(usize),
    /// The output expression of this column in the model's SQL.
    Output(String),
}

/// A related output location: the column whose output expression it points at, and its message.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RelatedOutput {
    pub column_name: String,
    pub message: String,
}

/// One contract diagnostic, in Python's emission order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractDiagnostic {
    pub code: &'static str,
    pub severity: ContractSeverity,
    pub message: String,
    pub column_name: Option<String>,
    pub location: ContractLocation,
    pub related_output: Option<RelatedOutput>,
    pub help: String,
}

/// Why native contract validation hands one model back to Python.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ContractDeferral {
    /// Native type normalization cannot reproduce Python for a compared type.
    TypeNormalization,
    /// A dynamic family name outside ASCII, whose `casefold` native does not reproduce.
    NonAsciiFamilyName,
}

impl ContractDeferral {
    /// The deferral kind recorded for the harness.
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Self::TypeNormalization => "type_normalization",
            Self::NonAsciiFamilyName => "non_ascii_family_name",
        }
    }
}

/// One model's contract outcome.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ContractOutcome {
    Diagnostics(Vec<ContractDiagnostic>),
    Deferred(ContractDeferral),
}

/// The inputs to table promotion conflict detection.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PromotionRequest {
    /// `settings.table_promotion_mode` when the project sets it.
    pub explicit_mode: Option<String>,
    /// The adapter's default table promotion mode.
    pub adapter_default: String,
    /// The configuration file the setting belongs to.
    pub settings_file: String,
    pub models: Vec<PromotionModel>,
}

/// One model's lifecycle config.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PromotionModel {
    pub name: String,
    /// The `contract` config value when it is a string.
    pub contract: Option<String>,
    /// The `materialized` config value (default `table`) when it is a string.
    pub materialized: Option<String>,
    /// The `incremental_mode` config value when it is a string.
    pub incremental_mode: Option<String>,
}

/// One K011 promotion conflict.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PromotionConflict {
    /// The index of the conflicting model in the request.
    pub model_index: usize,
    pub code: &'static str,
    pub message: String,
    pub help: String,
}
