//! Python's resource assembly loop over one project's sources, seeds and audits.

use std::cell::RefCell;

use crate::assembly::project::_helpers::deps::{audit_deps, reference_deps};
use crate::assembly::project::_helpers::syntax::syntax_valid;
use crate::assembly::project::_helpers::targets::{managed_source, seed_target};
use crate::assembly::project::_helpers::templates::TemplateInputs;
use crate::assembly::project::models::{
    ModelFacts, ProjectRequest, ProjectResources, ResourceFailure, ResourceSlot,
};

/// Each resource's facts in Python's assembly order (sources, seeds, audits) up to its failure.
pub(crate) fn project_resources(request: &ProjectRequest) -> ProjectResources {
    let target = request.target.as_ref();
    let inputs = TemplateInputs {
        variables: &request.variables,
        environment: &request.environment,
        reads: RefCell::new(Vec::new()),
    };
    let mut resources = ProjectResources {
        model_syntax_valid: request
            .models
            .iter()
            .map(|model| valid_syntax(model, &request.dialect))
            .collect(),
        model_deps: request
            .models
            .iter()
            .map(|model| reference_deps(&model.references))
            .collect(),
        function_deps: request
            .functions
            .iter()
            .map(|function| reference_deps(&function.references))
            .collect(),
        ..ProjectResources::default()
    };
    for (index, source) in request.sources.iter().enumerate() {
        match managed_source(source, target, &inputs) {
            Ok(namespace) => resources.sources.push(namespace),
            Err(error) => {
                let failure = ResourceFailure {
                    slot: ResourceSlot::Source,
                    index,
                    error,
                };
                return failed(resources, &inputs, failure);
            }
        }
    }
    for (index, seed) in request.seeds.iter().enumerate() {
        match seed_target(seed, &request.defaults, target, &inputs) {
            Ok(namespace) => resources.seeds.push(namespace),
            Err(error) => {
                let failure = ResourceFailure {
                    slot: ResourceSlot::Seed,
                    index,
                    error,
                };
                return failed(resources, &inputs, failure);
            }
        }
    }
    for (index, audit) in request.audits.iter().enumerate() {
        match audit_deps(audit) {
            Ok(keys) => resources.audit_deps.push(keys),
            Err(error) => {
                let failure = ResourceFailure {
                    slot: ResourceSlot::Audit,
                    index,
                    error,
                };
                return failed(resources, &inputs, failure);
            }
        }
    }
    resources.reads = inputs.reads.into_inner();
    resources
}

/// The resources assembled so far, the reads made and the resource Python raises at.
fn failed(
    mut resources: ProjectResources,
    inputs: &TemplateInputs<'_>,
    failure: ResourceFailure,
) -> ProjectResources {
    resources.reads = inputs.reads.borrow().clone();
    resources.failure = Some(failure);
    resources
}

/// Whether Python's model and hook syntax validation passes; Python reports every failure.
fn valid_syntax(model: &ModelFacts, dialect: &str) -> bool {
    model
        .syntax_checks
        .iter()
        .all(|check| syntax_valid(check, dialect) == Ok(true))
}
