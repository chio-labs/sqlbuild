//! Model column contracts and promotion conflicts for the preview compiler engine.

use pyo3::prelude::{Bound, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::contracts::main::evaluate_model_contracts::evaluate_model_contracts;
use sqlbuild_analysis::contracts::main::promotion_conflicts::promotion_conflicts;
use sqlbuild_analysis::contracts::models::{
    ContractDiagnostic, ContractModel, ContractRequest, ContractSchema, ContractSeverity,
    DeclaredColumn, DeclaredColumnFamily, DynamicContractProof, InferredOutputColumn,
    PromotionConflict, PromotionModel, PromotionRequest,
};

use sqlbuild_analysis::type_system::models::TypeNormalizationError;

use crate::bindings::_helpers::boundary::panics::compiler_error;
use crate::bindings::_helpers::type_system::normalization::normalization_error;
use crate::bindings::types::CompilerDetach;

/// `(name, type, not_null, declared_in_named_schema)`.
type DeclaredRow = (String, Option<String>, bool, bool);
/// `(columns, dynamic_columns, type_enforcement, named_schema)`.
type SchemaRow = (Vec<DeclaredRow>, Vec<(String, String)>, bool, bool);
/// `(output_proven, failure_reason, [(family, inferred_type)])`.
type ProofRow = (bool, Option<String>, Vec<(String, Option<String>)>);
/// `(name, contract, schema, inferred_columns, fast_lineage_has_star, proof, unchecked)`.
type ModelRow = (
    String,
    Option<String>,
    Option<SchemaRow>,
    Option<Vec<(String, Option<String>, bool)>>,
    bool,
    Option<ProofRow>,
    Vec<String>,
);
/// `(code, is_error, message, column, declared_index, output_column, related, help)`.
type DiagnosticRow = (
    &'static str,
    bool,
    String,
    Option<String>,
    Option<usize>,
    Option<String>,
    Option<(String, String)>,
    String,
);
/// `(name, contract, materialized, incremental_mode)`.
type PromotionModelRow = (String, Option<String>, Option<String>, Option<String>);

/// Evaluate every model's column contract, raising Python's type normalization error.
#[pyfunction]
fn evaluate_native_model_contracts(
    py: Python<'_>,
    request: (String, bool, Vec<ModelRow>),
) -> PyResult<Vec<Vec<DiagnosticRow>>> {
    let (dialect, implicit_column_contracts, models) = request;
    let request = ContractRequest {
        dialect,
        implicit_column_contracts,
        models: models.into_iter().map(contract_model).collect(),
    };
    let outcomes: Result<Vec<Vec<ContractDiagnostic>>, TypeNormalizationError> = py
        .compiler_detach(|| Ok(evaluate_model_contracts(&request)))
        .map_err(compiler_error)?;
    Ok(outcomes
        .map_err(|error| normalization_error(py, &error))?
        .into_iter()
        .map(|diagnostics| diagnostics.into_iter().map(diagnostic_row).collect())
        .collect())
}

/// The K011 conflicts of enforced contracts under immediate table promotion.
#[pyfunction]
fn native_promotion_conflicts(
    py: Python<'_>,
    request: (Option<String>, String, String, Vec<PromotionModelRow>),
) -> PyResult<Vec<(usize, &'static str, String, String)>> {
    let (explicit_mode, adapter_default, settings_file, models) = request;
    let request = PromotionRequest {
        explicit_mode,
        adapter_default,
        settings_file,
        models: models
            .into_iter()
            .map(
                |(name, contract, materialized, incremental_mode)| PromotionModel {
                    name,
                    contract,
                    materialized,
                    incremental_mode,
                },
            )
            .collect(),
    };
    let conflicts: Vec<PromotionConflict> = py
        .compiler_detach(|| Ok(promotion_conflicts(&request)))
        .map_err(compiler_error)?;
    Ok(conflicts
        .into_iter()
        .map(|conflict| {
            (
                conflict.model_index,
                conflict.code,
                conflict.message,
                conflict.help,
            )
        })
        .collect())
}

fn contract_model(
    (name, contract, schema, inferred, has_star, proof, unchecked): ModelRow,
) -> ContractModel {
    ContractModel {
        name,
        contract,
        schema: schema.map(contract_schema),
        inferred_columns: inferred.map(inferred_columns),
        fast_lineage_has_star: has_star,
        dynamic_proof: proof.map(|(output_proven, failure_reason, families)| {
            DynamicContractProof {
                output_proven,
                failure_reason,
                families,
            }
        }),
        unchecked_output_columns: unchecked,
    }
}

fn inferred_columns(columns: Vec<(String, Option<String>, bool)>) -> Vec<InferredOutputColumn> {
    columns
        .into_iter()
        .map(|(name, inferred_type, nullable)| InferredOutputColumn {
            name,
            inferred_type,
            nullable,
        })
        .collect()
}

fn contract_schema(
    (columns, dynamic_columns, type_enforcement, named_schema): SchemaRow,
) -> ContractSchema {
    ContractSchema {
        columns: columns
            .into_iter()
            .map(
                |(name, declared_type, not_null, declared_in_named_schema)| DeclaredColumn {
                    name,
                    declared_type,
                    not_null,
                    declared_in_named_schema,
                },
            )
            .collect(),
        dynamic_columns: dynamic_columns
            .into_iter()
            .map(|(name, declared_type)| DeclaredColumnFamily {
                name,
                declared_type,
            })
            .collect(),
        type_enforcement,
        named_schema,
    }
}

fn diagnostic_row(diagnostic: ContractDiagnostic) -> DiagnosticRow {
    let (declared_index, output_column) = diagnostic.location.into_parts();
    (
        diagnostic.code,
        diagnostic.severity == ContractSeverity::Error,
        diagnostic.message,
        diagnostic.column_name,
        declared_index,
        output_column,
        diagnostic
            .related_output
            .map(|related| (related.column_name, related.message)),
        diagnostic.help,
    )
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(evaluate_native_model_contracts, module)?)?;
    module.add_function(wrap_pyfunction!(native_promotion_conflicts, module)?)?;
    Ok(())
}
