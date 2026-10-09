use std::cell::RefCell;

use sqlbuild_model_config::templates::models::Scalar;

use crate::assembly::project::_helpers::deps::audit_deps;
use crate::assembly::project::_helpers::syntax::syntax_valid;
use crate::assembly::project::_helpers::targets::{managed_source, seed_target};
use crate::assembly::project::_helpers::templates::TemplateInputs;
use crate::assembly::project::main::check_sql_syntax::check_sql_syntax;
use crate::assembly::project::models::{
    AuditFacts, InputRead, Namespace, Reference, SeedDefaults, SeedFacts, SourceFacts, SyntaxCheck,
    TargetNamespace, Variable,
};
use crate::assembly::project::tests::test_types::{ExpectedNamespace, SeedSpec};
use crate::assembly::project::types::ObjectKey;

/// `(database, schema, loader schema)` of a selected target.
type TargetSpec = (
    Option<&'static str>,
    Option<&'static str>,
    Option<&'static str>,
);

pub(crate) fn deps(
    references: &[(&str, &str, Option<&str>)],
    attached: Option<(&str, &str)>,
) -> Option<Vec<ObjectKey>> {
    audit_deps(&AuditFacts {
        references: references.iter().map(reference).collect(),
        attached: attached.map(|(kind, name)| (kind.to_owned(), name.to_owned())),
    })
    .ok()
}

pub(crate) fn seed(
    seed: SeedSpec,
    defaults: ExpectedNamespace,
    target: Option<TargetSpec>,
) -> Option<Namespace> {
    let (name, database, schema) = seed;
    let (default_database, default_schema, seed_database, seed_schema) = defaults;
    seed_target(
        &SeedFacts {
            name: name.to_owned(),
            database: database.map(str::to_owned),
            schema: schema.map(str::to_owned),
        },
        &SeedDefaults {
            database: default_database.map(str::to_owned),
            schema: default_schema.map(str::to_owned),
            seed_database: seed_database.map(str::to_owned),
            seed_schema: seed_schema.map(str::to_owned),
        },
        target.map(namespace_target).as_ref(),
        &template_inputs(&variables()),
    )
    .ok()
}

/// The seed's namespace with `environment` set, and the reads its templates made.
pub(crate) fn seed_reads(
    seed: SeedSpec,
    environment: &[(String, Option<String>)],
) -> (Option<Namespace>, Vec<InputRead>) {
    let (name, database, schema) = seed;
    let variables: Vec<(String, Variable)> = variables();
    let inputs = TemplateInputs {
        variables: &variables,
        environment,
        reads: RefCell::new(Vec::new()),
    };
    let resolved = seed_target(
        &SeedFacts {
            name: name.to_owned(),
            database: database.map(str::to_owned),
            schema: schema.map(str::to_owned),
        },
        &SeedDefaults::default(),
        None,
        &inputs,
    )
    .ok();
    (resolved, inputs.reads.into_inner())
}

pub(crate) fn source(
    source: (bool, Option<&str>, Option<&str>),
    target: Option<TargetSpec>,
) -> Option<Option<(Option<String>, Option<String>)>> {
    let (managed, database, schema) = source;
    managed_source(
        &SourceFacts {
            name: "orders".to_owned(),
            managed,
            database: database.map(str::to_owned),
            schema: schema.map(str::to_owned),
        },
        target.map(namespace_target).as_ref(),
        &template_inputs(&variables()),
    )
    .ok()
}

pub(crate) fn valid(sql: &str, placeholders: &[(&str, &str)], dialect: &str) -> Option<bool> {
    syntax_valid(
        &SyntaxCheck {
            sql: sql.to_owned(),
            placeholders: placeholders
                .iter()
                .map(|(name, value)| ((*name).to_owned(), (*value).to_owned()))
                .collect(),
        },
        dialect,
    )
    .ok()
}

pub(crate) fn all_valid(sqls: &[&str]) -> Option<bool> {
    let checks: Vec<SyntaxCheck> = sqls
        .iter()
        .map(|sql| SyntaxCheck {
            sql: (*sql).to_owned(),
            placeholders: vec![("x".to_owned(), "1".to_owned())],
        })
        .collect();
    check_sql_syntax("generic", &checks).ok()
}

pub(crate) fn namespace(expected: ExpectedNamespace) -> Namespace {
    let (database, schema, logical_database, logical_schema) = expected;
    Namespace {
        database: database.map(str::to_owned),
        schema: schema.map(str::to_owned),
        logical_database: logical_database.map(str::to_owned),
        logical_schema: logical_schema.map(str::to_owned),
    }
}

fn reference(spec: &(&str, &str, Option<&str>)) -> Reference {
    let (kind, name, package) = spec;
    Reference {
        kind: (*kind).to_owned(),
        name: (*name).to_owned(),
        package: package.map(str::to_owned),
    }
}

fn namespace_target(spec: TargetSpec) -> TargetNamespace {
    let (database, schema, loader_schema) = spec;
    TargetNamespace {
        database: database.map(str::to_owned),
        schema: schema.map(str::to_owned),
        loader_schema: loader_schema.map(str::to_owned),
    }
}

fn template_inputs(variables: &[(String, Variable)]) -> TemplateInputs<'_> {
    TemplateInputs {
        variables,
        environment: &[],
        reads: RefCell::new(Vec::new()),
    }
}

fn variables() -> Vec<(String, Variable)> {
    vec![
        (
            "env_name".to_owned(),
            Variable::Scalar(Scalar::Text("prod".to_owned())),
        ),
        (
            "n".to_owned(),
            Variable::Scalar(Scalar::Text("3".to_owned())),
        ),
        ("flag".to_owned(), Variable::Scalar(Scalar::Bool(true))),
        ("tags".to_owned(), Variable::Unsupported),
    ]
}
