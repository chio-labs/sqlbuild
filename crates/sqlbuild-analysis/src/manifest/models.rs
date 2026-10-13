//! The compiled project, plan entries and Python-only facts a dbt-style manifest is built from.

use crate::assembly::project::types::ObjectKey;
use crate::python_values::models::PythonValue;

/// A compiled relation location.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ManifestRelationInput {
    pub database: Option<String>,
    pub schema: Option<String>,
    pub name: Option<String>,
    pub qualified_name: Option<String>,
}

/// A path's `str()`, its parent's parts and its stem.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ManifestPathInput {
    pub text: String,
    pub parent_parts: Vec<String>,
    pub stem: String,
}

/// An authored column.
#[derive(Clone, Debug, PartialEq)]
pub struct ManifestColumnInput {
    pub name: String,
    pub description: Option<String>,
    /// `dict(column.meta)` when the meta is truthy.
    pub meta: Option<PythonValue>,
    pub data_type: Option<String>,
}

/// One resolved lifecycle hook entry.
#[derive(Clone, Debug, PartialEq)]
pub enum ManifestHookInput {
    Sql {
        statement: String,
        name: Option<String>,
        /// `relative_path.as_posix()`.
        relative_path: Option<String>,
        definition_sql: Option<String>,
        kwargs: PythonValue,
        description: Option<String>,
    },
    Python {
        name: String,
        kwargs: PythonValue,
    },
    /// Any other entry, which serializations skip.
    Other,
}

/// The model config values the manifest reads, each as `values.get(key, default)` returned it.
#[derive(Clone, Debug, PartialEq)]
pub struct ManifestConfigInput {
    pub enabled: PythonValue,
    pub alias: PythonValue,
    pub schema: PythonValue,
    pub database: PythonValue,
    /// `str()` of each tag when the `tags` value is a list or tuple.
    pub tags: Option<Vec<String>>,
    /// `str()` of the `materialized` value, `view` when absent or `None`.
    pub materialized: String,
    pub incremental_strategy: PythonValue,
    pub merge_exclude_columns: PythonValue,
    pub full_refresh: PythonValue,
    pub unique_key: PythonValue,
    pub on_schema_change: PythonValue,
    /// The entries when the hooks value is a list or tuple.
    pub pre_hooks: Option<Vec<ManifestHookInput>>,
    pub post_hooks: Option<Vec<ManifestHookInput>>,
}

/// One dynamic column family of a model schema.
#[derive(Clone, Debug, PartialEq)]
pub struct ManifestDynamicColumnInput {
    pub name: PythonValue,
    pub pivot_column: PythonValue,
    pub value_column: PythonValue,
    pub aggregate: PythonValue,
    pub data_type: PythonValue,
    pub name_pattern: PythonValue,
}

/// A model's attached schema entry.
#[derive(Clone, Debug, PartialEq)]
pub struct ManifestModelSchemaInput {
    pub description: Option<String>,
    /// `dict(schema_entry.meta)` when the meta is not `None`.
    pub meta: Option<PythonValue>,
    pub columns: Vec<ManifestColumnInput>,
    pub dynamic_columns: Vec<ManifestDynamicColumnInput>,
}

/// A compiled model.
#[derive(Clone, Debug, PartialEq)]
pub struct ManifestModelInput {
    pub name: String,
    pub path: ManifestPathInput,
    pub destination: ManifestRelationInput,
    pub query_sql: String,
    pub config: ManifestConfigInput,
    pub schema: Option<ManifestModelSchemaInput>,
    pub deps: Vec<ObjectKey>,
}

/// A compiled source.
#[derive(Clone, Debug, PartialEq)]
pub struct ManifestSourceInput {
    /// The compiled source's name, which keys the `sources` map.
    pub name: String,
    pub path: String,
    pub entry_name: String,
    pub database: Option<String>,
    pub schema: Option<String>,
    pub table: Option<String>,
    pub description: Option<String>,
    /// `dict(entry.meta)` when the meta is truthy.
    pub meta: Option<PythonValue>,
    pub loader: Option<String>,
    pub write_strategy: Option<String>,
    pub cursor_column: Option<PythonValue>,
    /// The unique key, when truthy.
    pub unique_key: Option<PythonValue>,
    pub columns: Vec<ManifestColumnInput>,
}

/// A compiled seed.
#[derive(Clone, Debug, PartialEq)]
pub struct ManifestSeedInput {
    pub name: String,
    pub path: ManifestPathInput,
    pub destination: ManifestRelationInput,
    pub tags: Vec<String>,
    pub description: Option<String>,
    /// `dict(schema_entry.meta)` when the meta is truthy.
    pub meta: Option<PythonValue>,
    pub columns: Vec<ManifestColumnInput>,
}

/// A loaded macro, keyed by its registry name.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ManifestMacroInput {
    /// The registry name the macro is loaded under.
    pub key: String,
    pub name: String,
    pub relative_path: String,
    pub raw_source: String,
}

/// A macro declaration of the scope index.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ManifestMacroDeclarationInput {
    pub name: String,
    pub scope: String,
    pub owning_path: Option<String>,
    /// The macro's dependency names, when the record carries macro facts.
    pub dependencies: Option<Vec<String>>,
}

/// A SQL hook definition file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ManifestSqlHookInput {
    pub name: String,
    pub relative_path: String,
    pub sql_body: String,
    pub description: Option<String>,
}

/// A Python hook's path and source identity hashes.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ManifestPythonHookInput {
    pub name: String,
    pub relative_path: String,
    pub definition_hash: String,
    pub version_hash: String,
}

/// A planned audit.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ManifestAuditPlanInput {
    pub name: String,
    pub resolved_sql: String,
    pub attached_target_name: Option<String>,
    pub attached_column_name: Option<String>,
    pub scope_deps: Vec<ObjectKey>,
}

/// A planned SQL test.
#[derive(Clone, Debug, PartialEq)]
pub struct ManifestSqlTestPlanInput {
    pub key: ObjectKey,
    pub name: String,
    /// `(model name, resolved SQL)` of each chain step.
    pub chain: Vec<(String, String)>,
    pub scope_deps: Vec<ObjectKey>,
    pub source_path: Option<String>,
    pub block_index: PythonValue,
    pub parent_name: PythonValue,
    pub case_name: Option<String>,
    pub case_index: PythonValue,
    pub case_fingerprint: Option<String>,
    /// `(name, value type, nullable)` of each declared parameter.
    pub parameter_schema: Vec<(String, String, PythonValue)>,
    /// `(name, value)` of each bound parameter, decimals already as text.
    pub parameters: Vec<(String, PythonValue)>,
}

/// The plan entries a build manifest reads.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct ManifestPlanInput {
    /// `(model name, resolved SQL)` of each model entry.
    pub models: Vec<(String, String)>,
    pub source_load_names: Vec<String>,
    pub audits: Vec<ManifestAuditPlanInput>,
    pub sql_tests: Vec<ManifestSqlTestPlanInput>,
}

/// Everything the manifest is built from besides the graph.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct ManifestInput {
    pub project_name: String,
    pub adapter_type: String,
    pub run_id: String,
    /// `datetime.now(tz=UTC).isoformat()`.
    pub generated_at: String,
    pub sql_analysis_dialect: Option<String>,
    pub models: Vec<ManifestModelInput>,
    pub sources: Vec<ManifestSourceInput>,
    pub seeds: Vec<ManifestSeedInput>,
    pub macros: Vec<ManifestMacroInput>,
    pub macro_declarations: Vec<ManifestMacroDeclarationInput>,
    pub sql_hooks: Vec<ManifestSqlHookInput>,
    pub python_hooks: Vec<ManifestPythonHookInput>,
    pub plan: Option<ManifestPlanInput>,
}
