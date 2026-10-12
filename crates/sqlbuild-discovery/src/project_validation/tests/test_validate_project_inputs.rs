use crate::models::{DiscoveryFailure, FailureKind};
use crate::project_validation::main::validate_project_inputs::validate_project_inputs;
use crate::project_validation::models::{
    DependencyFact, ModelFact, NamedPath, NodeFact, NodeKind, ProjectFacts, SchemaFileFact,
    SeedEntryFact, SeedFileFact, SourceFact, SourceFileFact, ValidationFailure,
};

fn named(name: &str, path: &str) -> NamedPath {
    NamedPath {
        name: name.to_owned(),
        path: path.to_owned(),
    }
}

fn model(name: &str) -> ModelFact {
    ModelFact {
        file: named(name, &format!("models/{name}.sql")),
        local_declarations: Vec::new(),
    }
}

fn node(kind: NodeKind, name: &str, depends_on: Vec<DependencyFact>) -> NodeFact {
    NodeFact {
        kind,
        name: name.to_owned(),
        path: format!("python/{name}.py"),
        decorator_config: false,
        depends_on,
    }
}

fn on(owner: usize, name: &str) -> DependencyFact {
    DependencyFact::Object {
        owner: Some(owner),
        decorated_name: Some(name.to_owned()),
    }
}

fn failure(facts: &ProjectFacts) -> Option<(FailureKind, String)> {
    match validate_project_inputs(facts) {
        Ok(()) => None,
        Err(ValidationFailure::Discovery(DiscoveryFailure { kind, message, .. })) => {
            Some((kind, message))
        }
        Err(other) => panic!("unexpected failure: {other:?}"),
    }
}

struct ValidationTestCase {
    description: &'static str,
    facts: ProjectFacts,
    expected: Option<(FailureKind, &'static str)>,
}

#[test]
fn given_discovered_facts_when_validating_then_reports_python_first_conflict() {
    let test_cases = [
        ValidationTestCase {
            description: "a valid project passes",
            facts: ProjectFacts {
                models: vec![model("orders"), model("customers")],
                ..ProjectFacts::default()
            },
            expected: None,
        },
        ValidationTestCase {
            description: "a non-canonical model identity is rejected first",
            facts: ProjectFacts {
                models: vec![model("Orders"), model("_chain_")],
                ..ProjectFacts::default()
            },
            expected: Some((
                FailureKind::ResourceIdentity,
                "Invalid model identity 'Orders' in models/Orders.sql; use snake_case 'orders'",
            )),
        },
        ValidationTestCase {
            description: "a reserved model name fails its identity check first",
            facts: ProjectFacts {
                models: vec![model("_chain_")],
                ..ProjectFacts::default()
            },
            expected: Some((
                FailureKind::ResourceIdentity,
                "Invalid model identity '_chain_' in models/_chain_.sql; use snake_case 'chain'",
            )),
        },
        ValidationTestCase {
            description: "a source and a model share a logical relation name",
            facts: ProjectFacts {
                models: vec![model("orders")],
                sources: vec![SourceFileFact {
                    path: "sources/shop.yml".to_owned(),
                    entries: vec![SourceFact {
                        name: "orders".to_owned(),
                        ..SourceFact::default()
                    }],
                }],
                ..ProjectFacts::default()
            },
            expected: Some((
                FailureKind::Conflict,
                "Logical relation name 'orders' is declared as both model in models/orders.sql \
                 and source in sources/shop.yml",
            )),
        },
        ValidationTestCase {
            description: "a task cycle names its path",
            facts: ProjectFacts {
                nodes: vec![
                    node(NodeKind::Task, "extract", vec![on(1, "load")]),
                    node(NodeKind::Task, "load", vec![on(0, "extract")]),
                ],
                ..ProjectFacts::default()
            },
            expected: Some((
                FailureKind::Conflict,
                "Python node dependency cycle detected: extract -> load -> extract",
            )),
        },
        ValidationTestCase {
            description: "a check depending on a check",
            facts: ProjectFacts {
                nodes: vec![
                    node(NodeKind::Check, "first", Vec::new()),
                    node(NodeKind::Check, "second", vec![on(0, "first")]),
                ],
                ..ProjectFacts::default()
            },
            expected: Some((
                FailureKind::Conflict,
                "Check 'second' depends on another check; checks may depend on loaders, tasks, \
                 assets, models, sources, and seeds only",
            )),
        },
        ValidationTestCase {
            description: "an undeclared seed CSV",
            facts: ProjectFacts {
                seeds: vec![SeedFileFact {
                    file: named("countries", "seeds/countries.csv"),
                    absolute_path: "/missing/seeds/countries.csv".to_owned(),
                }],
                ..ProjectFacts::default()
            },
            expected: Some((
                FailureKind::Seed,
                "Seed CSV seeds/countries.csv has no matching declaration for seed 'countries' \
                 under seeds/**/*.yml",
            )),
        },
        ValidationTestCase {
            description: "an unmatched path default lists known folders",
            facts: ProjectFacts {
                models: vec![ModelFact {
                    file: named("orders", "models/marts/orders.sql"),
                    local_declarations: Vec::new(),
                }],
                path_default_keys: vec!["staging".to_owned()],
                ..ProjectFacts::default()
            },
            expected: Some((
                FailureKind::Conflict,
                "path_defaults['staging'] does not match any model paths. Known model folders \
                 include: marts",
            )),
        },
    ];
    for test_case in test_cases {
        let expected: Option<(FailureKind, String)> = test_case
            .expected
            .map(|(kind, message)| (kind, message.to_owned()));
        assert_eq!(
            failure(&test_case.facts),
            expected,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_a_seed_whose_header_differs_when_validating_then_reports_python_tuple_reprs() {
    let directory = tempfile::tempdir().unwrap();
    let csv_path = directory.path().join("countries.csv");
    std::fs::write(&csv_path, "code,label\nGB,United Kingdom\n").unwrap();
    let facts = ProjectFacts {
        seeds: vec![SeedFileFact {
            file: named("countries", "seeds/countries.csv"),
            absolute_path: csv_path.to_string_lossy().into_owned(),
        }],
        schemas: vec![SchemaFileFact {
            path: "seeds/countries.yml".to_owned(),
            model_names: Vec::new(),
            seeds: vec![SeedEntryFact {
                name: "countries".to_owned(),
                columns: vec!["code".to_owned()],
                ..SeedEntryFact::default()
            }],
        }],
        ..ProjectFacts::default()
    };

    let result = failure(&facts);

    assert_eq!(
        result,
        Some((
            FailureKind::Seed,
            "seeds/countries.csv header ('code', 'label') does not match declared seed columns \
             ('code',) for 'countries'"
                .to_owned()
        ))
    );
}

struct PathDefaultsTestCase {
    description: &'static str,
    model_paths: &'static [&'static str],
    keys: &'static [&'static str],
    expected_fragment: Option<&'static str>,
}

#[test]
fn given_path_defaults_when_validating_then_every_key_must_match_a_model_path() {
    let test_cases = [
        PathDefaultsTestCase {
            description: "accepts Windows-style model paths that match path defaults",
            model_paths: &["models\\staging\\orders.sql"],
            keys: &["staging"],
            expected_fragment: None,
        },
        PathDefaultsTestCase {
            description: "accepts recursive glob matching nested staging prefix",
            model_paths: &["models/commerce/partner_feed/staging/orders.sql"],
            keys: &["commerce/**/staging"],
            expected_fragment: None,
        },
        PathDefaultsTestCase {
            description: "accepts recursive glob matching zero segments",
            model_paths: &["models/commerce/staging/orders.sql"],
            keys: &["commerce/**/staging"],
            expected_fragment: None,
        },
        PathDefaultsTestCase {
            description: "counts broad glob as matched when a literal wins selection",
            model_paths: &["models/commerce/partner_feed/staging/orders.sql"],
            keys: &["commerce/**/staging", "commerce/partner_feed/staging"],
            expected_fragment: None,
        },
        PathDefaultsTestCase {
            description: "rejects recursive glob matching no model paths",
            model_paths: &["models/commerce/partner_feed/marts/orders.sql"],
            keys: &["commerce/**/staging"],
            expected_fragment: Some(
                "path_defaults['commerce/**/staging'] does not match any model paths",
            ),
        },
        PathDefaultsTestCase {
            description: "rejects equally specific matching globs during discovery",
            model_paths: &["models/commerce/eu/staging/orders.sql"],
            keys: &["commerce/*/staging", "commerce/eu/*"],
            expected_fragment: Some("matches equally specific path_defaults keys"),
        },
    ];
    for test_case in test_cases {
        let facts = ProjectFacts {
            models: test_case
                .model_paths
                .iter()
                .map(|path| ModelFact {
                    file: named("orders", path),
                    local_declarations: Vec::new(),
                })
                .collect(),
            path_default_keys: test_case.keys.iter().map(|key| (*key).to_owned()).collect(),
            ..ProjectFacts::default()
        };

        let result = failure(&facts);

        match test_case.expected_fragment {
            None => assert_eq!(result, None, "{}", test_case.description),
            Some(fragment) => {
                let (kind, message) = result.unwrap_or_else(|| panic!("{}", test_case.description));
                assert_eq!(kind, FailureKind::Conflict, "{}", test_case.description);
                assert!(
                    message.contains(fragment),
                    "{}: {message}",
                    test_case.description
                );
            }
        }
    }
}
