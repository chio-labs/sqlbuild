//! Python's `validate_discovered_resource_identities`: canonical identities, in discovery order.

use crate::models::{DiscoveryFailure, FailureKind};
use crate::project_validation::models::{NamedPath, ProjectFacts, ValidationFailure};
use sqlbuild_model_config::resource_identities::main::resource_identity_failure::resource_identity_failure;

/// One identity to check: its name, the kind the error names, its path and whether it is private.
struct Candidate<'a> {
    name: &'a str,
    kind: &'a str,
    path: &'a str,
    private: bool,
}

fn public<'a>(name: &'a str, kind: &'a str, path: &'a str) -> Candidate<'a> {
    Candidate {
        name,
        kind,
        path,
        private: false,
    }
}

fn named<'a>(entries: &'a [NamedPath], kind: &'a str) -> impl Iterator<Item = Candidate<'a>> {
    entries
        .iter()
        .map(move |entry| public(&entry.name, kind, &entry.path))
}

/// Reject the first identity that is not canonical lowercase snake_case.
pub(crate) fn validate_identities(facts: &ProjectFacts) -> Result<(), ValidationFailure> {
    for candidate in candidates(facts) {
        if let Some((corrected, help)) =
            resource_identity_failure(candidate.name, candidate.private)
        {
            return Err(ValidationFailure::Discovery(DiscoveryFailure {
                kind: FailureKind::ResourceIdentity,
                message: format!(
                    "Invalid {} identity '{}' in {}; use snake_case '{corrected}'",
                    candidate.kind, candidate.name, candidate.path
                ),
                help: Some(help),
            }));
        }
    }
    Ok(())
}

fn candidates(facts: &ProjectFacts) -> impl Iterator<Item = Candidate<'_>> {
    let models = facts.models.iter().flat_map(|model| {
        std::iter::once(public(&model.file.name, "model", &model.file.path)).chain(
            model
                .local_declarations
                .iter()
                .map(|declaration| Candidate {
                    name: &declaration.name,
                    kind: "model-local declaration",
                    path: &declaration.path,
                    private: true,
                }),
        )
    });
    let functions =
        named(&facts.sql_functions, "function").chain(named(&facts.python_functions, "function"));
    let seeds = facts
        .seeds
        .iter()
        .map(|seed| public(&seed.file.name, "seed", &seed.file.path));
    let schemas = facts.schemas.iter().flat_map(|schema| {
        let models = schema
            .model_names
            .iter()
            .map(move |name| public(name, "schema model", &schema.path));
        let seeds = schema
            .seeds
            .iter()
            .map(move |seed| public(&seed.name, "schema seed", &schema.path));
        models.chain(seeds)
    });
    let sources = facts.sources.iter().flat_map(|file| {
        file.entries
            .iter()
            .map(move |entry| public(&entry.name, "source", &file.path))
    });
    let tests = facts.tests.iter().flat_map(|test| {
        test.blocks.iter().flat_map(move |block| {
            let name: &str = block.name.as_deref().unwrap_or(&test.file.name);
            std::iter::once(public(name, "SQL test", &test.file.path)).chain(
                block
                    .cases
                    .iter()
                    .map(move |case| public(case, "SQL test case", &test.file.path)),
            )
        })
    });
    let audits = facts.audits.iter().flat_map(|audit| {
        audit.block_names.iter().flat_map(move |block_name| {
            let name: &str = if audit.generic {
                &audit.file.name
            } else {
                block_name.as_deref().unwrap_or(&audit.file.name)
            };
            let instance = block_name
                .as_deref()
                .filter(|_| audit.generic)
                .map(|instance| public(instance, "generic audit instance", &audit.file.path));
            std::iter::once(public(name, "audit", &audit.file.path)).chain(instance)
        })
    });
    let declarations = facts.declaration_files.iter().flat_map(|file| {
        file.declarations.iter().map(move |declaration| Candidate {
            name: &declaration.name,
            kind: "declaration",
            path: &declaration.path,
            private: file.private,
        })
    });
    let nodes = ["loader", "task", "asset", "check"]
        .into_iter()
        .flat_map(move |label| {
            facts
                .nodes
                .iter()
                .filter(move |node| node.kind.label() == label)
                .map(move |node| public(&node.name, label, &node.path))
        });
    models
        .chain(functions)
        .chain(named(&facts.sql_hooks, "SQL hook"))
        .chain(seeds)
        .chain(schemas)
        .chain(sources)
        .chain(tests)
        .chain(named(&facts.scenarios, "scenario"))
        .chain(audits)
        .chain(declarations)
        .chain(named(&facts.model_schemas, "model schema"))
        .chain(named(&facts.materializations, "materialization"))
        .chain(nodes)
        .chain(named(&facts.hook_functions, "Python hook"))
        .chain(named(&facts.event_exporters, "event exporter"))
        .chain(named(&facts.providers, "provider"))
}
