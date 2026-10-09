//! Python's `promotion_conflict_diagnostics_impl`: enforced contracts under immediate promotion.

use crate::contracts::_helpers::setting_help::{
    join_helps, setting_help, setting_note, snippet_help,
};
use crate::contracts::constants::{
    CONTRACT_ENFORCED, IMMEDIATE_PROMOTION_MODE, MICROBATCH_INCREMENTAL_MODE,
    PROMOTION_CONFLICT_CODE, PROMOTION_REMOVE_CONTRACT_HELP, SETTINGS_SECTION,
    STAGED_LIFECYCLE_MATERIALIZATIONS, STAGED_PROMOTION_MODE, TABLE_PROMOTION_MODE_SETTING_KEY,
};
use crate::contracts::models::{PromotionConflict, PromotionModel, PromotionRequest};

/// One conflict per enforced-contract table model when the effective promotion is immediate.
pub(crate) fn promotion_conflicts(request: &PromotionRequest) -> Vec<PromotionConflict> {
    let effective: &str = request
        .explicit_mode
        .as_deref()
        .unwrap_or(&request.adapter_default);
    if effective != IMMEDIATE_PROMOTION_MODE {
        return Vec::new();
    }
    let help: String = conflict_help(request);
    request
        .models
        .iter()
        .enumerate()
        .filter(|(_, model)| uses_staged_table_lifecycle(model))
        .map(|(model_index, model)| PromotionConflict {
            model_index,
            code: PROMOTION_CONFLICT_CODE,
            message: format!(
                "model '{}': contract enforced requires staged table promotion; immediate table \
                 promotion cannot validate runtime output before target mutation",
                model.name
            ),
            help: help.clone(),
        })
        .collect()
}

fn uses_staged_table_lifecycle(model: &PromotionModel) -> bool {
    model.contract.as_deref() == Some(CONTRACT_ENFORCED)
        && model
            .materialized
            .as_deref()
            .is_some_and(|materialized| STAGED_LIFECYCLE_MATERIALIZATIONS.contains(&materialized))
        && model.incremental_mode.as_deref() != Some(MICROBATCH_INCREMENTAL_MODE)
}

fn conflict_help(request: &PromotionRequest) -> String {
    let explicit: bool = request.explicit_mode.is_some();
    let file: &str = &request.settings_file;
    let current: String = setting_note(
        file,
        SETTINGS_SECTION,
        TABLE_PROMOTION_MODE_SETTING_KEY,
        IMMEDIATE_PROMOTION_MODE,
        explicit,
    ) + "; enforced contracts are validated in a staging table before promotion";
    let staged_fix: String = if explicit && request.adapter_default == STAGED_PROMOTION_MODE {
        snippet_help(
            "remove that line to use the default staged promotion",
            &format!("or set this in {file}"),
            &[
                format!("[{SETTINGS_SECTION}]"),
                format!("{TABLE_PROMOTION_MODE_SETTING_KEY} = \"{STAGED_PROMOTION_MODE}\""),
            ],
        )
    } else {
        setting_help(
            "to validate enforced contracts before promotion",
            file,
            SETTINGS_SECTION,
            TABLE_PROMOTION_MODE_SETTING_KEY,
            STAGED_PROMOTION_MODE,
        )
    };
    join_helps(&[
        current,
        staged_fix,
        PROMOTION_REMOVE_CONTRACT_HELP.to_owned(),
    ])
}
