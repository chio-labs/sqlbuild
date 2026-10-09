//! Python's `evaluate_model_contracts`: every model's column contract diagnostics, in order.

use crate::contracts::_helpers::columns::{
    declared_shape_validation_is_active, model_contract_diagnostics, requires_contract_evaluation,
};
use crate::contracts::models::{ContractOutcome, ContractRequest};

/// One outcome per requested model; models that need no evaluation have no diagnostics.
#[must_use]
pub fn evaluate_model_contracts(request: &ContractRequest) -> Vec<ContractOutcome> {
    let implicit: bool = request.implicit_column_contracts;
    request
        .models
        .iter()
        .map(|model| {
            if !requires_contract_evaluation(model, implicit) {
                return ContractOutcome::Diagnostics(Vec::new());
            }
            match model_contract_diagnostics(
                model,
                declared_shape_validation_is_active(model, implicit),
                &request.dialect,
            ) {
                Ok(diagnostics) => ContractOutcome::Diagnostics(diagnostics),
                Err(deferral) => ContractOutcome::Deferred(deferral),
            }
        })
        .collect()
}
