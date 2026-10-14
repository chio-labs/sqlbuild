//! Help for SQL the parser rejects: the exact header, project and single-run opt-outs.

use crate::assembly::project::constants::{
    MODEL_OPT_OUT_HELP, PROJECT_AND_RUN_OPT_OUT_HELP, REPORT_ONLY_HELP,
};

/// The opt-out help; only SQL a model owns offers the MODEL header entry.
#[must_use]
pub fn sql_analysis_opt_out_help(model_owned: bool) -> String {
    let first: &str = if model_owned {
        MODEL_OPT_OUT_HELP
    } else {
        REPORT_ONLY_HELP
    };
    format!("{first}{PROJECT_AND_RUN_OPT_OUT_HELP}")
}
