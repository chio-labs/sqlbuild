//! Python's resource assembly facts for one project, or why Python must assemble it.

use std::cell::RefCell;

use sqlbuild_core::constants::PANIC_MESSAGE;
use sqlbuild_core::panics::main::catch_compiler_panic::catch_compiler_panic;

use crate::assembly::project::_helpers::deps::{audit_deps, reference_deps};
use crate::assembly::project::_helpers::syntax::syntax_valid;
use crate::assembly::project::_helpers::targets::{managed_source, seed_target};
use crate::assembly::project::_helpers::templates::TemplateInputs;
use crate::assembly::project::constants::PANIC_DEFERRAL;
use crate::assembly::project::models::{ModelFacts, ProjectRequest, ProjectResources};
use crate::assembly::project::types::Fact;

/// Each resource's dependencies and namespace, or the kind of work Python must do instead.
pub fn assemble_project_resources(request: &ProjectRequest) -> Result<ProjectResources, String> {
    catch_compiler_panic(|| resources(request)).map_err(|kind| {
        if kind == PANIC_MESSAGE {
            PANIC_DEFERRAL.to_owned()
        } else {
            kind
        }
    })
}

fn resources(request: &ProjectRequest) -> Fact<ProjectResources> {
    let model_syntax_valid: Vec<bool> = request
        .models
        .iter()
        .map(|model| valid_syntax(model, &request.dialect))
        .collect();
    let target = request.target.as_ref();
    let inputs = TemplateInputs {
        variables: &request.variables,
        environment: &request.environment,
        reads: RefCell::new(Vec::new()),
    };
    let sources = request
        .sources
        .iter()
        .map(|source| managed_source(source, target, &inputs))
        .collect::<Fact<_>>()?;
    let seeds = request
        .seeds
        .iter()
        .map(|seed| seed_target(seed, &request.defaults, target, &inputs))
        .collect::<Fact<_>>()?;
    Ok(ProjectResources {
        model_syntax_valid,
        model_deps: request
            .models
            .iter()
            .map(|model| reference_deps(&model.references))
            .collect(),
        sources,
        seeds,
        function_deps: request
            .functions
            .iter()
            .map(|function| reference_deps(&function.references))
            .collect(),
        audit_deps: request.audits.iter().map(audit_deps).collect::<Fact<_>>()?,
        reads: inputs.reads.into_inner(),
    })
}

/// Whether Python's model and hook syntax validation passes; where it raises, Python's
/// validation runs for that model and reports the failure.
fn valid_syntax(model: &ModelFacts, dialect: &str) -> bool {
    model
        .syntax_checks
        .iter()
        .all(|check| syntax_valid(check, dialect) == Ok(true))
}
