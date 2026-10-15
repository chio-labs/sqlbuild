//! The synthetic package and dependency-first execution order of project macro modules.

use crate::macro_modules::_helpers::load_plan::{load_order, parent_packages, synthetic_root};
use crate::macro_modules::models::{MacroLoadPlan, MacroModuleSpec};

/// Root package named by a content digest, parent packages, and Kahn order with smallest name first.
#[must_use]
pub fn macro_load_plan(modules: &[MacroModuleSpec]) -> MacroLoadPlan {
    let root: String = synthetic_root(modules);
    MacroLoadPlan {
        packages: parent_packages(&root, modules),
        order: load_order(modules),
        root,
    }
}
